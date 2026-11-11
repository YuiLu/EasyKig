"""Transparent non-AI fallback for prototype parameter editing.

Replace this module with your own remote vision-language or geometry editor.
Only whitelisted, supplied Shape Keys can ever be changed.
"""
from typing import Mapping

# Positive (increase) and negative (decrease) natural-language instructions.
# For unspecified or ambiguous text this module returns no changes rather than inventing edits.
_ALIASES = {
    'Face Width': ('脸宽','臉寬','face width','wider face','narrower face'),
    'Cheek Fullness': ('脸颊','臉頰','cheek','cheeks','肉脸'),
    'Chin Length': ('下巴','chin'),
    'Forehead Height': ('额头','額頭','forehead'),
    'Eye Size': ('眼睛','眼形','eyes','eye size'),
    'Eye Spacing': ('眼距','眼睛间距','眼睛間距','eye spacing','eyes apart'),
    'Nose Projection': ('鼻子','nose'),
    'Mouth Curve': ('嘴角','微笑','smile','mouth'),
}

_NEGATIVE = ('小一点','小一些','小点','窄','缩','縮','短','降低','减少','減少',
             '收窄','浅','淺','less','smaller','narrower','shorter','decrease','reduce','lower')
_POSITIVE = ('大一点','大一些','大点','宽','寬','圆','圓','长','長','更多','增加',
             '丰满','飽滿','翘','翹','更高','more','bigger','larger','wider','longer','increase','fuller')


def _direction(fragment: str):
    low = fragment.lower()
    pos = any(w in low for w in _POSITIVE)
    neg = any(w in low for w in _NEGATIVE)
    if pos == neg:
        return 0
    return 1 if pos else -1


def propose_edits(prompt: str, shape_keys: Mapping[str,float], ranges: Mapping[str,list]):
    edits=dict(shape_keys)
    changed={}
    # Instructions are split at natural clause boundaries. Avoid applying an instruction
    # for one feature to every key mentioned elsewhere in the prompt.
    clauses=[x.strip() for x in __import__('re').split(r'[,，。;；\n]+',prompt) if x.strip()]
    for clause in clauses:
        direction=_direction(clause)
        if not direction:
            continue
        for key in shape_keys:
            aliases=_ALIASES.get(key,())
            if not any(alias.lower() in clause.lower() for alias in aliases):
                continue
            lo,hi=ranges.get(key,[0.0,1.0])
            lo,hi=float(lo),float(hi)
            if lo>=hi:
                continue
            current=float(edits[key])
            new=round(min(hi,max(lo,current+direction*.18*(hi-lo))),4)
            if new != current:
                edits[key]=new
                changed[key]=new
    return edits,changed
