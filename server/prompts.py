"""Built-in image prompts and optional server-local reference presets."""

import os
from pathlib import Path

WHITE_TO_FINISHED_PROMPT = """You are creating a concept preview of a handcrafted animegao kigurumi head mask.
Use the first attached image as the PRIMARY geometry/camera reference. Preserve its head outline,
facial proportions, exact viewing angle, nose and mouth positions, and eye socket placement.
Show the same mask after professional hand-finishing: smooth painted skin, fitted anime eye
artwork, brows, a realistic styled synthetic wig, fine blush, and studio product lighting.
Do NOT redesign the underlying white mesh or introduce a new pose, camera, expression or face shape.
This is an ILLUSTRATIVE concept image, not a dimensionally accurate simulation or manufacturing proof.
If a second image is provided it is a CHARACTER COLOR/STYLE reference only and must not override
geometry from the first image. No watermarks, collage, text labels or additional people.
Customer directions: {details}
"""


def finishing_prompt(details: str) -> str:
    details = ' '.join(details.strip().split())[:1500] or 'pastel skin, gentle blush, neatly styled wig'
    return WHITE_TO_FINISHED_PROMPT.format(details=details)


HEAD_REFERENCE_PROMPT = """Use the supplied anime character image as the appearance reference.
Create a neutral, unobstructed studio turnaround sheet of ONLY the character head: front,
left three-quarter, side, and rear. Move hair so that the face contour can be inspected.
Keep the character identity, eye color, hairstyle and palette consistent between views.
Keep each view at a matching scale with simple, clean lighting and no extra figures.
This is concept art; do not claim metric 3D correctness. User direction: {details}
"""

KIG_DESIGN_PROMPT = """Based on the supplied character head reference, depict a tangible
animegao kigurumi mask design as a clean four-view studio concept sheet. The face should
be a smooth, stylized, hard shell with a readable eye-opening concept and subtle nose
and mouth sculpt. Keep face proportions consistent across all views. Show front, three-
quarter, side and rear at matching scales. This is a design image, NOT a printable mesh.
Avoid human skin realism, body shots, captions and decorative backgrounds.
User direction: {details}
"""

PRODUCT_PROMPT = """Create a studio product reference from the supplied kigurumi mask design.
Show the same finished mask from the front, three-quarter, side and rear on a clean backdrop.
Preserve the sculpt, eyes, expression, colors and wig across views. User direction: {details}
"""


def reference_prompt(stage: str, details: str) -> str:
    prompts = {'head': HEAD_REFERENCE_PROMPT, 'design': KIG_DESIGN_PROMPT, 'product': PRODUCT_PROMPT}
    prompt = prompts[stage]
    directory = os.getenv('EASYKIG_REFERENCE_PROMPTS_DIR')
    if directory:
        # Preserve the supplied preset without newline conversion or templating.
        prompt = (Path(directory) / f'{stage}.txt').read_bytes().decode('utf-8')
        if not prompt.strip() or len(prompt) > 32000:
            raise ValueError(f'Invalid reference preset for {stage}')
        return prompt
    details = ' '.join(details.strip().split())[:1500] or 'preserve the original character identity'
    return prompt.format(details=details)
