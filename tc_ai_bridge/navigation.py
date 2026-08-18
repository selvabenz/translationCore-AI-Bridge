from __future__ import annotations

import ctypes
import os
import re
import time
import uuid
from dataclasses import dataclass

_REF_RE = re.compile(r'^([1-4]?[A-Z]{2,4})\s+(\d+):([0-9]+[A-Za-z]?)$', re.I)


def normalize_reference(reference: str) -> str:
    text = ' '.join(str(reference or '').strip().upper().split())
    m = _REF_RE.match(text)
    if not m:
        return ''
    book, chapter, verse = m.groups()
    return f'{book} {int(chapter)}:{verse.lower() if verse[-1:].isalpha() else int(verse)}'


@dataclass(frozen=True)
class NavigationEvent:
    reference: str
    origin: str
    request_id: str
    timestamp: float


class NavigationBroker:
    """Small deterministic echo/duplicate guard for Bridge, Paratext and Logos.

    Connectors do not directly forward events to one another. The Bridge owns the current
    reference. Every accepted external change enters through this broker, then the UI loads the
    verse and broadcasts the new current reference to every *other* enabled connector.
    """

    def __init__(self, *, echo_window_seconds: float = 2.5, settling_window_seconds: float = 1.4, clock=time.monotonic):
        self.echo_window_seconds = float(echo_window_seconds)
        self.settling_window_seconds = min(float(settling_window_seconds), self.echo_window_seconds)
        self._clock = clock
        self.current_reference = ''
        self.current_origin = 'bridge'
        self._outbound: dict[str, tuple[str, str, float, bool, str]] = {}
        self._observed: dict[str, str] = {}
        # A rejected external candidate stays suppressed while the surrounding Bridge context is
        # unchanged (for example dirty alignment the reviewer chose not to discard). If that
        # context changes, the same still-visible external reference may safely be offered again.
        self._rejected: dict[str, tuple[str, str]] = {}

    def new_event(self, reference: str, origin: str, *, context: str = '') -> NavigationEvent | None:
        ref = normalize_reference(reference)
        if not ref:
            return None
        origin = str(origin or 'bridge').lower()
        now = self._clock()
        # An exact reference sent to a connector moments ago is an echo, not a new user action.
        sent = self._outbound.get(origin)
        if sent and (now - sent[2]) <= self.echo_window_seconds:
            sent_ref, sent_id, sent_at, confirmed, prior_observed = sent
            if sent_ref == ref:
                # The connector has reached the reference we asked it to show. From this point
                # a *different* reference can immediately be treated as a real user change.
                self._outbound[origin] = (sent_ref, sent_id, sent_at, True, prior_observed)
                self._observed[origin] = ref
                return None
            if (not confirmed and prior_observed and ref == prior_observed
                    and (now - sent_at) <= self.settling_window_seconds):
                # A polled connector can briefly report its previous verse while an outbound
                # navigation is still settling. Do not bounce that stale observation back to
                # the other applications. After the short settling window, fail open so a
                # genuine user change or failed navigation is not suppressed indefinitely.
                # Forget the old observed value so that the same differing state can become a
                # real event after the settling window if the connector never confirms target.
                self._observed.pop(origin, None)
                return None
        # Polling the same unchanged connector state repeatedly is not a navigation event. A
        # previously rejected candidate is the one exception: if the Bridge context has changed
        # (dirty state resolved, project selection changed, project list changed, etc.), retry it.
        observed = self._observed.get(origin)
        rejected = self._rejected.get(origin)
        if observed == ref:
            if not (rejected and rejected[0] == ref and rejected[1] != str(context or '')):
                return None
            self._rejected.pop(origin, None)
        elif rejected and rejected[0] != ref:
            self._rejected.pop(origin, None)
        self._observed[origin] = ref
        if self.current_reference == ref:
            return None
        event = NavigationEvent(ref, origin, uuid.uuid4().hex, now)
        self.current_reference = ref
        self.current_origin = origin
        return event

    def commit_event(self, event: NavigationEvent) -> None:
        """Commit a candidate after the Bridge actually loaded the requested destination."""
        origin = str(event.origin or '').lower()
        self._rejected.pop(origin, None)
        self.current_reference = normalize_reference(event.reference)
        self.current_origin = origin or 'bridge'

    def reject_event(self, event: NavigationEvent, bridge_reference: str = '', *, context: str = '') -> None:
        """Roll broker state back when an external candidate could not be loaded.

        Keep the connector's observed value so polling does not repeatedly prompt the reviewer.
        The same reference becomes eligible again when ``context`` changes or when the external
        application first moves to another reference and later returns.
        """
        origin = str(event.origin or '').lower()
        ref = normalize_reference(event.reference)
        if origin and ref:
            self._observed[origin] = ref
            self._rejected[origin] = (ref, str(context or ''))
        actual = normalize_reference(bridge_reference)
        self.current_reference = actual
        self.current_origin = 'bridge'

    def clear_rejection(self, origin: str = '') -> None:
        key = str(origin or '').lower()
        if key:
            self._rejected.pop(key, None)
            return
        self._rejected.clear()

    def set_bridge_reference(self, reference: str, origin: str = 'bridge', request_id: str = '') -> NavigationEvent | None:
        ref = normalize_reference(reference)
        if not ref:
            return None
        event = NavigationEvent(ref, str(origin or 'bridge').lower(), request_id or uuid.uuid4().hex, self._clock())
        self.current_reference = ref
        self.current_origin = event.origin
        self._observed['bridge'] = ref
        return event

    def observe_state(self, target: str, reference: str) -> str:
        """Seed a connector's last known state without treating it as user navigation."""
        ref = normalize_reference(reference)
        if ref:
            self._observed[str(target or '').lower()] = ref
        return ref

    def record_outbound(self, target: str, reference: str, request_id: str = '') -> str:
        ref = normalize_reference(reference)
        if not ref:
            return ''
        rid = request_id or uuid.uuid4().hex
        target_key = str(target or '').lower()
        self._outbound[target_key] = (ref, rid, self._clock(), False, self._observed.get(target_key, ''))
        return rid

    def is_recent_outbound(self, target: str, reference: str) -> bool:
        ref = normalize_reference(reference)
        sent = self._outbound.get(str(target or '').lower())
        return bool(ref and sent and sent[0] == ref and (self._clock() - sent[2]) <= self.echo_window_seconds)


class NavigationOwnership:
    """Per-Windows-user mutex preventing two Bridge processes from driving navigation.

    The mutex is acquired only when external verse synchronization is enabled. A second Bridge
    window remains fully usable, but cannot own Paratext/Logos navigation until the first releases
    it. Non-Windows builds fail open because the external desktop connectors are Windows-only.
    """

    DEFAULT_NAME = r'Local\translationCoreAIBridge.NavigationOwner'
    WAIT_OBJECT_0 = 0x00000000
    WAIT_ABANDONED = 0x00000080

    def __init__(self, name: str = DEFAULT_NAME):
        self.name = str(name)
        self._handle = None
        self._owned = False

    @property
    def owned(self) -> bool:
        return bool(self._owned)

    def acquire(self) -> bool:
        if self._owned:
            return True
        if os.name != 'nt':
            self._owned = True
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            return False
        result = int(kernel32.WaitForSingleObject(handle, 0))
        if result not in (self.WAIT_OBJECT_0, self.WAIT_ABANDONED):
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        self._owned = True
        return True

    def release(self) -> None:
        if not self._owned:
            return
        handle, self._handle = self._handle, None
        self._owned = False
        if os.name == 'nt' and handle:
            try:
                ctypes.windll.kernel32.ReleaseMutex(handle)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

    def close(self) -> None:
        self.release()
