import bpy


class EASYKIG_PT_main(bpy.types.Panel):
    bl_label = 'EasyKig'
    bl_idname = 'EASYKIG_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EasyKig'

    def draw(self, context):
        s=context.scene.easykig_settings
        col=self.layout.column(align=True)
        col.label(text='Design prototype / 非制造级', icon='ERROR')
        col.label(text='1. Import / Select', icon='IMPORT')
        col.prop(s,'pmx_meters_per_unit')
        col.operator('easykig.import_pmx', icon='IMPORT')
        row=col.row(align=True)
        row.operator('easykig.create_demo',text='Demo Template')
        row.operator('easykig.pick_face',text='Use Selected')
        col.operator('easykig.guess_face',text='Guess Face Mesh')
        col.prop(s,'face')
        col.prop(s,'template_collection')
        col.operator('easykig.split_materials',text='Split By Material (Copy)')
        col.operator('easykig.make_working_copy',text='Bake Working Copy')

        col.separator()
        col.label(text='2. Morph / Template',icon='MOD_LATTICE')
        obj=s.face
        if obj and obj.type=='MESH' and obj.data.shape_keys:
            if obj.data.shape_keys.use_relative:
                for key in obj.data.shape_keys.key_blocks[1:]:
                    col.prop(key,'value',text=key.name,slider=True)
            else:
                col.prop(obj.data.shape_keys,'eval_time',text='Evaluation Time')
        else:
            col.label(text='Select a mesh with Shape Keys',icon='INFO')
        col.prop(s,'editing_prompt',text='Text Edit')
        col.operator('easykig.ai_morph',text='Remote Text -> Shape Keys',icon='FILE_REFRESH')

        col.separator()
        col.label(text='3. Geometry / Output',icon='MOD_SOLIDIFY')
        col.operator('easykig.set_units')
        col.prop(s,'height_mm')
        col.operator('easykig.resize_height')
        col.prop(s,'shell_thickness_mm')
        col.operator('easykig.add_solidify')
        col.operator('easykig.basic_mesh_check')
        col.operator('easykig.export_stl',icon='EXPORT')
        col.label(text='Export not certified print-ready',icon='ERROR')

        col.separator()
        col.label(text='4. White -> Finished Preview',icon='RENDER_STILL')
        col.prop(s,'preview_output_dir')
        col.operator('easykig.render_white',text='Render White Clay')
        col.prop(s,'reference_image')
        col.prop(s,'expression_image')
        col.prop(s,'character_image')
        col.prop(s,'shell_example_image')
        row=col.row(align=True)
        row.operator('easykig.reference_design',text='Character Head').stage='head'
        row.operator('easykig.reference_design',text='Kig Design').stage='design'
        row.operator('easykig.reference_design',text='Product').stage='product'
        row=col.row(align=True)
        row.operator('easykig.open_image',text='Head').kind='head'
        row.operator('easykig.open_image',text='Design').kind='design'
        row.operator('easykig.open_image',text='Product').kind='product'
        col.prop(s,'finishing_prompt')
        col.operator('easykig.render_finished',text='Generate Finished Preview',icon='IMAGE_DATA')
        row=col.row(align=True)
        row.operator('easykig.open_image',text='White Image').kind='white'
        row.operator('easykig.open_image',text='Finished Image').kind='finished'
        col.label(text='AI preview is illustrative only',icon='INFO')

        col.separator()
        col.label(text='5. Remote 3D Service',icon='URL')
        try:
            addon=context.preferences.addons.get(__package__)
            if addon:
                col.prop(addon.preferences,'server_url',text='Server')
        except Exception:
            pass
        col.operator('easykig.health',text='Test Connection',icon='CHECKMARK')
        col.operator('easykig.remote_mesh_edit',text='Remote Edit Mesh (GLB)',icon='MOD_MESHDEFORM')
        col.label(text='Mesh sent only when button clicked',icon='INFO')


def register():
    bpy.utils.register_class(EASYKIG_PT_main)


def unregister():
    bpy.utils.unregister_class(EASYKIG_PT_main)
