import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty, StringProperty


def reset_reference_results(settings, _context):
    settings.last_head_png = ''
    settings.last_design_png = ''
    settings.last_product_png = ''


class EASYKIG_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    server_url: StringProperty(
        name="3D Editing Server URL",
        description="Remote server root, e.g. https://your-domain.example. Never include credentials in URL",
        default="http://127.0.0.1:8000",
    )
    server_token: StringProperty(name="Server Token", subtype="PASSWORD", default="")
    timeout_seconds: FloatProperty(name="Request Timeout (s)", default=360, min=5, max=600)
    image_model: StringProperty(
        name="Image Model", maxlen=160,
        description="Model ID allowed by the gateway. Leave blank to use its default",
    )
    preview_directory: StringProperty(
        name="Preview Folder Override", subtype="DIR_PATH",
        description="Leave blank to use the project's preview folder",
    )

    def draw(self, context):
        col = self.layout.column(align=True)
        col.prop(self, "server_url")
        col.prop(self, "server_token")
        col.prop(self, "timeout_seconds")
        col.prop(self, "image_model")
        col.prop(self, "preview_directory")
        col.operator("easykig.health", text="Test Connection", icon='CHECKMARK')


class EASYKIG_Settings(bpy.types.PropertyGroup):
    face: PointerProperty(name="Face / Template", type=bpy.types.Object)
    template_collection: PointerProperty(
        name="Preview Collection", type=bpy.types.Collection,
        description="Include other meshes from this collection in white previews",
    )
    pmx_meters_per_unit: FloatProperty(
        name="PMX Scale (m / unit)", default=.08, min=.0001, max=10, precision=4,
    )
    height_mm: FloatProperty(name="Target Height (mm)", default=260, min=100, max=600)
    shell_thickness_mm: FloatProperty(name="Shell Thickness (mm)", default=2.0, min=0.5, max=12)
    preview_output_dir: StringProperty(name="Preview Directory", default="//easykig_outputs", subtype="DIR_PATH")
    reference_image: StringProperty(
        name="Reference Image", subtype="FILE_PATH", update=reset_reference_results,
    )
    expression_image: StringProperty(name="Expression Reference", subtype="FILE_PATH")
    character_image: StringProperty(name="Character Colors Reference", subtype="FILE_PATH")
    shell_example_image: StringProperty(name="Shell / Product Example", subtype="FILE_PATH")
    finishing_prompt: StringProperty(
        name="Finish Description", default="soft pink skin, anime eyes, delicate blush, styled wig, premium handcrafted cosplay kigurumi mask",
    )
    editing_prompt: StringProperty(name="Shape Edit Instruction", default="脸颊更圆一点，眼睛大一点")
    last_head_png: StringProperty(name="Head Reference", default="")
    last_design_png: StringProperty(name="Kigurumi Design", default="")
    last_product_png: StringProperty(name="Product Reference", default="")
    last_white_png: StringProperty(name="White Render", default="")
    last_finished_png: StringProperty(name="Finished Preview", default="")
    result_view: EnumProperty(
        name="Preview",
        items=[
            ('head', 'Head', 'Character head reference'),
            ('design', 'Design', 'Kigurumi design reference'),
            ('product', 'Product', 'Product reference'),
            ('white', 'White Clay', 'White clay render'),
            ('finished', 'Finished', 'Finished preview'),
        ],
        default='finished',
    )


_CLASSES = (EASYKIG_AddonPreferences, EASYKIG_Settings)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.easykig_settings = PointerProperty(type=EASYKIG_Settings)


def unregister():
    del bpy.types.Scene.easykig_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
