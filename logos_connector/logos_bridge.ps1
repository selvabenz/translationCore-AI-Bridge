# translationCore AI Bridge v0.7.5 - local Logos COM helper
# Local-only stdio bridge. No network listener and no Logos credentials are used.
#
# Logos exposes the full automation surface through its registered type library. On some
# current Windows/Logos combinations PowerShell can create the Launcher but cannot marshal
# the richer COM interfaces returned by LogosApplication. This helper therefore imports the
# registered Logos type library into a temporary .NET interop assembly and invokes members
# through those COM-imported interface definitions. PowerShell only handles JSON/stdin/stdout.
# It never edits the registry and never writes Scripture.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class LogosTypedInterop
{
    private static readonly object Gate = new object();
    private static Assembly _interop;
    private static object _launcher;
    private static object _application;
    private static string _launcherInterface = "";
    private static string _applicationInterface = "";
    private static string _logosComPath = "";

    private enum RegKind
    {
        Default = 0,
        Register = 1,
        None = 2
    }

    [DllImport("oleaut32.dll", CharSet = CharSet.Unicode, PreserveSig = true)]
    private static extern int LoadTypeLibEx(string file, RegKind regKind, out ITypeLib typeLib);

    [DllImport("ole32.dll")]
    private static extern int CoCreateInstance(
        [In] ref Guid rclsid,
        IntPtr pUnkOuter,
        uint dwClsContext,
        [In] ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out object ppv);

    private sealed class ImportSink : ITypeLibImporterNotifySink
    {
        public void ReportEvent(ImporterEventKind eventKind, int eventCode, string eventMsg) { }
        public Assembly ResolveRef(object typeLib) { return null; }
    }

    private static string LogosComPath()
    {
        if (!String.IsNullOrEmpty(_logosComPath)) return _logosComPath;
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string path = Path.Combine(local, "Logos", "System", "LogosCom.exe");
        if (!File.Exists(path))
            throw new FileNotFoundException("Logos COM type library was not found.", path);
        _logosComPath = path;
        return path;
    }

    private static Assembly EnsureInterop()
    {
        lock (Gate)
        {
            if (_interop != null) return _interop;

            string logosCom = LogosComPath();
            ITypeLib typeLib;
            int hr = LoadTypeLibEx(logosCom, RegKind.None, out typeLib);
            if (hr < 0 || typeLib == null)
                Marshal.ThrowExceptionForHR(hr);

            // ConvertTypeLibToAssembly returns an in-memory AssemblyBuilder. We intentionally
            // keep it in-process; we do not report or depend on a DLL that was never persisted.
            string assemblyName = "Interop.Logos4Lib.InMemory.dll";
            TypeLibConverter converter = new TypeLibConverter();
            _interop = converter.ConvertTypeLibToAssembly(
                typeLib,
                assemblyName,
                TypeLibImporterFlags.None,
                new ImportSink(),
                null,
                null,
                "Logos4Lib",
                null);

            if (_interop == null || !_interop.GetTypes().Any())
                throw new InvalidOperationException("The Logos type library could not be imported into .NET.");
            return _interop;
        }
    }

    private static bool SupportsInterface(object target, Type candidate)
    {
        if (target == null || candidate == null || !candidate.IsInterface || candidate.GUID == Guid.Empty)
            return false;
        IntPtr unk = IntPtr.Zero;
        IntPtr ptr = IntPtr.Zero;
        try
        {
            unk = Marshal.GetIUnknownForObject(target);
            Guid iid = candidate.GUID;
            int hr = Marshal.QueryInterface(unk, ref iid, out ptr);
            return hr >= 0 && ptr != IntPtr.Zero;
        }
        catch { return false; }
        finally
        {
            if (ptr != IntPtr.Zero) Marshal.Release(ptr);
            if (unk != IntPtr.Zero) Marshal.Release(unk);
        }
    }

    private static IEnumerable<Type> CompatibleInterfaces(object target)
    {
        return EnsureInterop().GetTypes()
            .Where(t => t.IsInterface && SupportsInterface(target, t))
            .OrderBy(t => t.Name, StringComparer.OrdinalIgnoreCase);
    }

    private static PropertyInfo FindProperty(object target, string propertyName, out Type owner)
    {
        foreach (Type t in CompatibleInterfaces(target))
        {
            PropertyInfo p = t.GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public);
            if (p != null) { owner = t; return p; }
            // COM-imported interfaces may inherit members from another imported interface.
            foreach (Type inherited in t.GetInterfaces())
            {
                p = inherited.GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public);
                if (p != null && SupportsInterface(target, inherited)) { owner = inherited; return p; }
            }
        }
        owner = null;
        return null;
    }

    private static MethodInfo FindMethod(object target, string methodName, int argCount, out Type owner)
    {
        foreach (Type t in CompatibleInterfaces(target))
        {
            MethodInfo m = t.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(x => String.Equals(x.Name, methodName, StringComparison.OrdinalIgnoreCase) && x.GetParameters().Length == argCount);
            if (m != null) { owner = t; return m; }
            foreach (Type inherited in t.GetInterfaces())
            {
                m = inherited.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                    .FirstOrDefault(x => String.Equals(x.Name, methodName, StringComparison.OrdinalIgnoreCase) && x.GetParameters().Length == argCount);
                if (m != null && SupportsInterface(target, inherited)) { owner = inherited; return m; }
            }
        }
        owner = null;
        return null;
    }

    private static string InterfaceSummary(object target, params string[] interestingMembers)
    {
        try
        {
            List<string> names = new List<string>();
            foreach (Type t in CompatibleInterfaces(target))
            {
                bool relevant = interestingMembers == null || interestingMembers.Length == 0;
                if (!relevant)
                {
                    foreach (string name in interestingMembers)
                    {
                        if (t.GetMember(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.IgnoreCase).Length > 0)
                        { relevant = true; break; }
                    }
                }
                if (relevant) names.Add(t.FullName ?? t.Name);
            }
            return String.Join(", ", names.Take(8).ToArray());
        }
        catch { return ""; }
    }

    private static object Get(object target, string propertyName)
    {
        if (target == null) return null;
        Type owner;
        PropertyInfo p = FindProperty(target, propertyName, out owner);
        if (p != null) return p.GetValue(target, null);

        MethodInfo getter = FindMethod(target, "get_" + propertyName, 0, out owner);
        if (getter != null) return getter.Invoke(target, new object[0]);

        throw new MissingMemberException(
            propertyName + " was not found on a COM interface supported by this Logos object. Compatible interfaces: " +
            InterfaceSummary(target, propertyName));
    }

    private static object Call(object target, string methodName, params object[] args)
    {
        if (target == null) return null;
        object[] actual = args ?? new object[0];
        Type owner;
        MethodInfo m = FindMethod(target, methodName, actual.Length, out owner);
        if (m != null) return m.Invoke(target, actual);
        throw new MissingMemberException(
            methodName + " was not found on a COM interface supported by this Logos object. Compatible interfaces: " +
            InterfaceSummary(target, methodName));
    }

    private static void Set(object target, string propertyName, object value)
    {
        if (target == null) throw new ArgumentNullException("target");
        Type owner;
        PropertyInfo p = FindProperty(target, propertyName, out owner);
        if (p != null && p.CanWrite) { p.SetValue(target, value, null); return; }
        MethodInfo setter = FindMethod(target, "set_" + propertyName, 1, out owner);
        if (setter != null) { setter.Invoke(target, new object[] { value }); return; }
        throw new MissingMemberException(propertyName + " could not be written on the Logos COM object.");
    }

    private static int Count(object collection)
    {
        return Convert.ToInt32(Get(collection, "Count"));
    }

    private static object Item(object collection, int index)
    {
        if (collection == null) return null;
        Type owner;
        PropertyInfo p = FindProperty(collection, "Item", out owner);
        if (p != null && p.GetIndexParameters().Length == 1)
            return p.GetValue(collection, new object[] { index });
        MethodInfo m = FindMethod(collection, "get_Item", 1, out owner) ?? FindMethod(collection, "Item", 1, out owner);
        if (m != null) return m.Invoke(collection, new object[] { index });
        throw new MissingMemberException("Item was not found on the Logos COM collection.");
    }

    private static object EnsureLauncher()
    {
        if (_launcher != null) return _launcher;
        EnsureInterop();
        Type comType = Type.GetTypeFromProgID("LogosBibleSoftware.Launcher", false);
        if (comType == null) throw new InvalidOperationException("The Logos COM launcher is not registered with Windows.");
        _launcher = Activator.CreateInstance(comType);
        _launcherInterface = InterfaceSummary(_launcher, "Application", "LaunchApplication");
        return _launcher;
    }

    private static object ReadApplication()
    {
        object launcher = EnsureLauncher();
        object app = Get(launcher, "Application");
        if (app != null)
            _applicationInterface = InterfaceSummary(app, "ApiVersion", "DataTypes", "GetOpenPanels");
        return app;
    }

    private static object GetApplication()
    {
        try
        {
            _application = ReadApplication();
            return _application;
        }
        catch
        {
            ResetComObjects();
            _application = ReadApplication();
            return _application;
        }
    }

    private static void ResetComObjects()
    {
        _application = null;
        _launcher = null;
        _launcherInterface = "";
        _applicationInterface = "";
        GC.Collect();
        GC.WaitForPendingFinalizers();
    }

    private static string S(object value)
    {
        return value == null ? "" : Convert.ToString(value) ?? "";
    }

    private static Dictionary<string, object> BaseState(bool detected, bool connected, bool ready, int apiVersion, string message)
    {
        return new Dictionary<string, object> {
            {"ok", true}, {"detected", detected}, {"connected", connected}, {"navigation_ready", ready},
            {"api_version", apiVersion}, {"reference_rendered", ""}, {"book_abbrev", ""},
            {"chapter", ""}, {"verse", ""}, {"panel_title", ""}, {"panel_kind", ""},
            {"message", message ?? ""}, {"interop_mode", "in-memory TypeLibConverter"},
            {"logos_com_path", _logosComPath ?? ""}, {"launcher_interfaces", _launcherInterface ?? ""},
            {"application_interfaces", _applicationInterface ?? ""}
        };
    }

    private static Dictionary<string, object> BibleReferenceFromPanel(object panel)
    {
        if (panel == null) return null;
        object refs = Call(panel, "GetCurrentReferencesAndHeadwords");
        if (refs == null) return null;
        int count = Count(refs);
        for (int i = 0; i < count; i++)
        {
            object entry = Item(refs, i);
            object reference = Get(entry, "Reference");
            if (reference == null) continue;

            string detailsKind = "";
            try { detailsKind = S(Get(reference, "DetailsKind")); } catch { }
            bool isBible = String.Equals(detailsKind, "Bible", StringComparison.OrdinalIgnoreCase);
            if (!isBible)
            {
                object dt = null;
                try { dt = Get(reference, "DataType"); } catch { }
                string alias = "";
                if (dt != null) { try { alias = S(Get(dt, "Alias")); } catch { } }
                isBible = alias.StartsWith("Bible", StringComparison.OrdinalIgnoreCase);
            }
            if (!isBible) continue;

            object start = null;
            try { start = Get(reference, "RangeStart"); } catch { }
            if (start == null) start = reference;
            object details = Get(start, "Details");
            if (details == null) continue;

            string rendered = "";
            try { rendered = S(Call(reference, "Render", "long")); } catch { }
            string title = "";
            string kind = "";
            try { title = S(Get(panel, "Title")); } catch { }
            try { kind = S(Get(panel, "Kind")); } catch { }
            return new Dictionary<string, object> {
                {"reference_rendered", rendered},
                {"book_abbrev", S(Get(details, "Book"))},
                {"chapter", S(Get(details, "Chapter"))},
                {"verse", S(Get(details, "Verse"))},
                {"panel_title", title},
                {"panel_kind", kind}
            };
        }
        return null;
    }

    private static void Merge(Dictionary<string, object> target, Dictionary<string, object> source)
    {
        if (source == null) return;
        foreach (KeyValuePair<string, object> kv in source) target[kv.Key] = kv.Value;
    }

    public static Dictionary<string, object> Diagnose()
    {
        lock (Gate)
        {
            Dictionary<string, object> result = BaseState(false, false, false, 0, "");
            try
            {
                object launcher = EnsureLauncher();
                result["detected"] = true;
                result["launcher_interfaces"] = InterfaceSummary(launcher, "Application", "LaunchApplication");
                object app = ReadApplication();
                result["application_interfaces"] = InterfaceSummary(app, "ApiVersion", "DataTypes", "GetOpenPanels", "Navigate");
                result["ok"] = true;
                result["message"] = "Logos COM interface discovery completed.";
                return result;
            }
            catch (Exception ex)
            {
                result["ok"] = false;
                result["error"] = ex.Message;
                return result;
            }
        }
    }

    public static Dictionary<string, object> GetState()
    {
        lock (Gate)
        {
            try
            {
                object app = GetApplication();
                if (app == null)
                    return BaseState(false, false, false, 0, "Logos is not running or is not ready.");

                int apiVersion = Convert.ToInt32(Get(app, "ApiVersion"));
                if (apiVersion < 1)
                    return BaseState(true, false, false, apiVersion, "Unsupported Logos COM API version: " + apiVersion.ToString());

                object dataTypes = Get(app, "DataTypes");
                if (dataTypes == null)
                    return BaseState(true, false, false, apiVersion, "Logos DataTypes is unavailable.");
                object bible = Call(dataTypes, "GetDataType", "Bible");
                if (bible == null)
                    return BaseState(true, false, false, apiVersion, "The Logos Bible data type is unavailable.");

                object panels = Call(app, "GetOpenPanels");
                Dictionary<string, object> state = BaseState(true, true, true, apiVersion, "");

                object active = null;
                try { active = Call(app, "GetActivePanel"); } catch { }
                Dictionary<string, object> found = BibleReferenceFromPanel(active);
                if (found != null) { Merge(state, found); return state; }

                if (panels != null)
                {
                    int count = Count(panels);
                    for (int i = 0; i < count; i++)
                    {
                        object panel = Item(panels, i);
                        found = BibleReferenceFromPanel(panel);
                        if (found != null) { Merge(state, found); return state; }
                    }
                }

                state["message"] = "Logos navigation is ready. Open a Bible resource to enable Logos to Bridge reference tracking.";
                return state;
            }
            catch (TargetInvocationException tie)
            {
                Exception inner = tie.InnerException ?? tie;
                return BaseState(true, false, false, 0, "Logos COM call failed: " + inner.Message);
            }
            catch (Exception ex)
            {
                return BaseState(true, false, false, 0, "Logos connector failed: " + ex.Message);
            }
        }
    }

    public static Dictionary<string, object> Navigate(string referenceText)
    {
        lock (Gate)
        {
            if (String.IsNullOrWhiteSpace(referenceText))
                throw new ArgumentException("No Scripture reference was supplied.");

            object app = GetApplication();
            if (app == null) throw new InvalidOperationException("Logos is not running or is not ready.");
            int apiVersion = Convert.ToInt32(Get(app, "ApiVersion"));
            if (apiVersion < 1) throw new InvalidOperationException("Unsupported Logos COM API version: " + apiVersion.ToString());

            object dataTypes = Get(app, "DataTypes");
            object bible = Call(dataTypes, "GetDataType", "Bible");
            if (bible == null) throw new InvalidOperationException("The Logos Bible data type is unavailable.");
            object reference = Call(bible, "ParseReference", referenceText);
            if (reference == null) throw new InvalidOperationException("Logos could not parse Scripture reference: " + referenceText);
            object request = Call(app, "CreateNavigationRequest");
            if (request == null) throw new InvalidOperationException("Logos could not create a navigation request.");
            Set(request, "Reference", reference);
            Call(app, "Navigate", request);
            return GetState();
        }
    }
}
'@

function Write-BridgeResponse([hashtable]$response) {
    [Console]::Out.WriteLine(($response | ConvertTo-Json -Compress -Depth 8))
    [Console]::Out.Flush()
}

while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    try {
        $request = $line | ConvertFrom-Json
        $action = [string]$request.action
        switch ($action) {
            'state' {
                $state = [LogosTypedInterop]::GetState()
                Write-BridgeResponse $state
            }
            'diagnose' {
                $diag = [LogosTypedInterop]::Diagnose()
                Write-BridgeResponse $diag
            }
            'navigate' {
                $result = [LogosTypedInterop]::Navigate([string]$request.reference)
                $result['origin_id'] = [string]$request.origin_id
                Write-BridgeResponse $result
            }
            'close' {
                Write-BridgeResponse @{ ok = $true; closed = $true }
                break
            }
            default {
                Write-BridgeResponse @{ ok = $false; error = ('Unsupported Logos bridge action: ' + $action) }
            }
        }
        if ($action -eq 'close') { break }
    } catch {
        $message = [string]$_.Exception.Message
        if ($_.Exception.InnerException) { $message = $message + ' | ' + [string]$_.Exception.InnerException.Message }
        Write-BridgeResponse @{ ok = $false; error = $message }
    }
}
