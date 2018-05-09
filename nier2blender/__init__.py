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
    if "wmb_importer" in locals():
        from nier2blender import wmb_importer
        importlib.reload(wmb_importer)
        print("[Info] reload <wmb_importer> module.")
    if "mot_importer" in locals():
        from nier2blender import mot_importer
        importlib.reload(mot_importer)
        print("[Info] reload <mot_importer> module.")

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
                print('[Info] Selected obj: %s' % (obj.name))
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

# store keymaps here to access after registration
addon_keymaps = []

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import)

    # handle the keymap
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km_importWMB = km.keymap_items.new(ImportNier2blender.bl_idname, 'W', 'PRESS', ctrl=True, shift=True)
    km_importMotion = km.keymap_items.new(ImportNierMotion2blender.bl_idname, 'M', 'PRESS', ctrl=True, shift=True)
    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)

    # handle the keymap
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    # clear the list
    del addon_keymaps[:]


if __name__ == '__main__':
    register()
