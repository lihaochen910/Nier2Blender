bl_info = {
    "name": "Nier: Automata model importer",
    "author": "C4nf3ng",
    "version": (1, 1),
    "blender": (2, 78, 0),
    "api": 38019,
    "location": "File > Import-Export",
    "description": "Import Nier:Automata wmb model data",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

# To support reload properly, try to access a package var,
# if it's there, reload everything
if "bpy" in locals():
    import importlib
    if "gtb_importer" in locals():
        from nier2blender import wmb_importer
        from nier2blender import mot_importer
        importlib.reload(wmb_importer)
        importlib.reload(mot_importer)

#just for Break

import bpy
from bpy_extras.io_utils import ExportHelper,ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty

class ImportNier2blender(bpy.types.Operator, ImportHelper):
    '''Load a Nier: Automata WMB File.'''
    bl_idname = "import.wmb_data"
    bl_label = "Import WMB Data"
    bl_options = {'PRESET'}
    filename_ext = ".wmb"
    filter_glob = StringProperty(default="*.wmb", options={'HIDDEN'})

    def execute(self, context):
        from nier2blender import wmb_importer
        return wmb_importer.main( self.filepath)

class ImportNierMotion2blender(bpy.types.Operator, ImportHelper):
    '''Load a Nier: Automata Motion File.'''
    bl_idname = "import.mot_data"
    bl_label = "Import MOT Data"
    bl_options = {'PRESET'}
    filename_ext = ".mot"
    filter_glob = StringProperty(default="*.mot", options={'HIDDEN'})

    def execute(self, context):
        armature = None
        for obj in context.selected_objects:
            if obj.get("bone_mapping"):
                armature = obj
                break

        if armature is None:
            print('[Error] context.selected_objects not found: bone_mapping')
            self.report({'ERROR'}, "No armature is selected!")
            return {'FINISHED'}

        from nier2blender import mot_importer
        return mot_importer.main(self.filepath, armature)


# Registration

def menu_func_import(self, context):
    self.layout.operator(ImportNier2blender.bl_idname, text="WMB File for Nier: Automata (.wmb)")
    self.layout.operator(ImportNierMotion2blender.bl_idname,
                         text="MOT File for Nier: Automata (.mot)")


def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)


if __name__ == '__main__':
    register()
