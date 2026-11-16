"""EasyKig built-in image prompts shared by Blender and the gateway."""

from typing import Literal


Component = Literal['front_face', 'hair_accessory', 'rigid_front_hair']
COMPONENT_LABELS = {
    'front_face': 'Front Face',
    'hair_accessory': 'Hair Accessory',
    'rigid_front_hair': 'Rigid Front Hair',
}

WHITE_TO_FINISHED_PROMPT = """You are creating a concept preview of a handcrafted animegao kigurumi head mask.
Use the first attached image as the PRIMARY geometry/camera reference. Preserve its head outline,
facial proportions, exact viewing angle, nose and mouth positions, and eye socket placement.
Show the same mask after professional hand-finishing: smooth painted skin, fitted anime eye
artwork, brows, a realistic styled synthetic wig, fine blush, and studio product lighting.
Do NOT redesign the underlying white mesh or introduce a new pose, camera, expression or face shape.
This is an ILLUSTRATIVE concept image, not a dimensionally accurate simulation or manufacturing proof.
Treat all images after the first as CHARACTER COLOR/STYLE references only. Preserve the geometry
from the first image. No watermarks, collage, text labels or additional people.
Customer directions: {details}
"""


def finishing_prompt(details: str) -> str:
    details = details.strip()[:1500] or 'pastel skin, gentle blush, neatly styled wig'
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
    details = details.strip()[:1500] or 'preserve the original character identity'
    return prompt.format(details=details)


_COMPONENT_SUBJECTS = {
    'front_face': (
        'the detached front face plate of the animegao kigurumi shell. Keep its stylized eyes, expression, '
        'skin finish, shallow nose and mouth, and outer face-plate contour. Recover obscured areas as '
        'smooth face shell. Exclude all hair, head ornaments, rear shell, neck, and mannequin stand'
    ),
    'hair_accessory': (
        'one detached hair ornament. Select the ornament identified by the part notes, or the most prominent '
        'ornament visible in the supplied reference. Keep its individual silhouette, colors and materials. '
        'Exclude the head, wig, strands, other ornaments, and stand. Stay faithful to an existing ornament'
    ),
    'rigid_front_hair': (
        'the detached, rigid molded fringe over the forehead. Keep the reference fringe silhouette, '
        'main sculpted locks, and color. Exclude face, rear hair, long wig lengths, hair accessories, and stand'
    ),
}


def component_reference_prompt(part: Component, details: str) -> str:
    return (
        'Use the supplied finished kigurumi product photo or product sheet to make a studio reference of '
        f'only {_COMPONENT_SUBJECTS[part]}. '
        'From a sheet, use its front view and use other views only to understand the part. '
        'Output one centered, fully visible frontal view of the individual piece on a plain light gray background. '
        'Keep the appearance of a physical, hard-surface product. No assembly, additional views, text or collage. '
        f'Apply part notes within the selected piece: {details.strip()[:1500] or "match the product reference"}'
    )


def component_target_prompt(part: Component, details: str) -> str:
    return (
        'Edit IMAGE 1, the white-clay render of the single template mesh. IMAGE 2 is the isolated design '
        f'reference. The only subject is {_COMPONENT_SUBJECTS[part]}. '
        'Match IMAGE 1 exactly for camera, framing, orientation and part scale. '
        'Use IMAGE 2 for color, finish and localized shape changes to the selected part. Preserve the '
        'template attachment boundary, cutouts and fitting edges where visible. Keep the full outline readable. '
        'Output one edited view at the same angle, with a plain neutral background. '
        'Exclude any missing assembly parts, props, floating shapes, text and multi-view layouts. '
        f'Apply part notes within these limits: {details.strip()[:1500] or "match the isolated reference"}'
    )
