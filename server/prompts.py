"""Server-local reference presets with a built-in fallback."""

import os
from pathlib import Path

from easykig.image_prompts import finishing_prompt
from easykig.image_prompts import reference_prompt as built_in_reference_prompt


def reference_prompt(stage: str, details: str) -> str:
    directory = os.getenv('EASYKIG_REFERENCE_PROMPTS_DIR')
    if directory:
        # Preserve the supplied preset without newline conversion or templating.
        prompt = (Path(directory) / f'{stage}.txt').read_bytes().decode('utf-8')
        if not prompt.strip() or len(prompt) > 32000:
            raise ValueError(f'Invalid reference preset for {stage}')
        return prompt
    return built_in_reference_prompt(stage, details)
