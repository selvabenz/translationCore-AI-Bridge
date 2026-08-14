from __future__ import annotations

from dataclasses import dataclass

# Prices are deliberately configurable and kept in one place. Defaults reflect the
# GPT-5.6 family pricing current when v0.6 was built; users can override in settings.
DEFAULT_PRICES = {
    'gpt-5.6-sol': {'input': 5.00, 'cached_input': 0.50, 'output': 30.00},
    'gpt-5.6': {'input': 5.00, 'cached_input': 0.50, 'output': 30.00},
    'gpt-5.6-terra': {'input': 2.00, 'cached_input': 0.20, 'output': 12.00},
    'gpt-5.6-luna': {'input': 0.20, 'cached_input': 0.02, 'output': 1.20},
}

@dataclass(frozen=True)
class ModelChoice:
    model: str
    reasoning_effort: str
    task: str
    rationale: str

class ModelRouter:
    def __init__(self, profile: str='balanced', explicit_model: str=''):
        self.profile=profile if profile in ('economy','balanced','quality','fixed') else 'balanced'
        self.explicit_model=explicit_model.strip()

    def choose(self,task:str,severity:str='medium',ambiguous:bool=False) -> ModelChoice:
        task=task.lower(); severity=severity.lower()
        if self.profile=='fixed' and self.explicit_model:
            return ModelChoice(self.explicit_model,'medium',task,'Fixed model selected by user')
        hard=severity in ('critical','high') or ambiguous or task in ('final_review','critical_review','theology','difficult_exegesis')
        if self.profile=='quality':
            return ModelChoice('gpt-5.6-sol','high' if hard else 'medium',task,'Quality-first routing')
        if self.profile=='economy':
            if hard: return ModelChoice('gpt-5.6-terra','medium',task,'Escalated from economy tier for difficult review')
            return ModelChoice('gpt-5.6-luna','low',task,'High-volume economy routing')
        # balanced
        if hard: return ModelChoice('gpt-5.6-sol','high',task,'Escalated for high-severity/ambiguous review')
        if task in ('alignment','selection','spelling','punctuation','terminology_scan'):
            return ModelChoice('gpt-5.6-luna','low',task,'Fast structured preparation task')
        return ModelChoice('gpt-5.6-terra','medium',task,'Balanced quality/cost routing')


def estimate_cost(model:str,input_tokens:int,output_tokens:int,cached_input_tokens:int=0,prices=None) -> float:
    prices=prices or DEFAULT_PRICES; p=prices.get(model) or prices.get('gpt-5.6-sol')
    fresh=max(0,input_tokens-cached_input_tokens)
    return (fresh*p['input'] + cached_input_tokens*p['cached_input'] + output_tokens*p['output'])/1_000_000.0
