import sys
import os
import numpy
import math
import nier2blender.mot as MOT
import bmesh
import bpy
import mathutils

SIGN = b"mot\x00"

def read_track(motReader, offset, count):
    # read tracks
    tracks = []
    data_offsets = []
    for trk_idx in range(count):
        motReader.seek(offset + trk_idx * 0xc)
        track = MOT.Track()
        track.read(motReader)
        track.adjust_offset(offset + trk_idx * 0xc)
        tracks.append(track)
        if track.offset > 0:
            data_offsets.append(track.offset)
    dummy_track = MOT.Track()
    dummy_track.read(motReader)
    dummy_track.adjust_offset(offset + count * 0xc)
    
    # calculate track chunk data
    data_offsets.append(motReader.size)
    data_offsets.sort()
    offset_size = {}
    for i in range(len(data_offsets) - 1):
        data_size = data_offsets[i + 1] - data_offsets[i]
        offset_size[data_offsets[i]] = data_size

    # if compress type == 0, then it is a constant value
    for trk_idx in range(count):
        track = tracks[trk_idx]
        if track.offset > 0:
            size = offset_size[track.offset]
            if track.comtype in (6, 7):
                 assert size == align4(0xc + track.keycount * 0x4)
            elif track.comtype == 5:
                assert size == align4(0x18 + track.keycount * 0x8)
            elif track.comtype == 3:
                assert size == align4(0x4 + track.keycount * 0x1)
            elif track.comtype == 2:
                assert size == align4(0x8 + track.keycount * 0x2)
            elif track.comtype == 8:
                # 6 unsigned short + (unsigned short frameIndex + 3 byte coeffs)
                assert size == align4(0xc + track.keycount * 0x5)
            elif track.comtype == 4:
                # no header + 0x10
                assert size == align4(0x0 + track.keycount * 0x10)
            elif track.comtype == 1:
                # floats
                assert size == align4(0x0 + track.keycount * 0x4)
            else:
                 assert False, "unknown compression type %d" % (track.comtype)

    hdr_offset = offset
    for trk_idx in range(count):
        track = tracks[trk_idx]
        if track.comtype != 0:
            size = offset_size[track.offset]
        else:
            size = 0
            
        # print ("Track %d hdr@0x%x, size=0x%x" % (trk_idx, hdr_offset, size),)
        # print (track)
        
        if track.offset:
            track.parse_keyframes(motReader)
        hdr_offset += 0xc
        
    # print ("Dummy Track @ 0x%x" % hdr_offset,)
    # print (dummy_track)
    
    return tracks

def read_motionData(frame_count, tracks):
    """read motion data from tracks"""
    # {bone_id: [POSX, POSY, POSZ, ROTX, ROTY, ROTZ, SCALEX, SCALEY, SCALEZ]}
    evaluated_tracks = {}

    # evaluate all tracks for all bones
    for track in tracks:
        bone_tracks = evaluated_tracks.setdefault(track.bone_id, [None] * 9)
        # print('bone_id:%d' % (track.bone_id))
        # Some mot file have unknown track type: 14,15
        if track.type >= 0 and track.type <= 9:
            frames = []
            for i in range(frame_count):
                frames.append(track.eval(i))
            bone_tracks[track.type] = frames
        else:
            print('[Error] Unknown TrackType:%d' % (track.type))

    # fill in missing tracks
    default_value = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    for bone_id, bone_tracks in evaluated_tracks.items():
        for i in range(len(bone_tracks)):
            if bone_tracks[i] is None:
                bone_tracks[i] = [default_value[i]] * frame_count

    # combine separated tracks
    motion_data = {}
    for bone_id, bone_tracks in evaluated_tracks.items():
        pos_frames = []
        rot_frames = []
        scale_frames = []

        for i in range(frame_count):
            pos_frames.append(
                (i, bone_tracks[0][i], bone_tracks[1][i], bone_tracks[2][i]))
            rotx = bone_tracks[3][i]
            roty = bone_tracks[4][i]
            rotz = bone_tracks[5][i]
            # TODO: need to convert euler angles to quaternion
            x, y, z, w = euler_angle_to_quaternion(rotx, roty, rotz)
            rot_frames.append((i, x, y, z, w))
            # print(rot_frames)
            scale_frames.append(
                (i, bone_tracks[6][i], bone_tracks[7][i], bone_tracks[8][i]))

        # print(rot_frames)

        motion_data[bone_id] = [
            pos_frames,
            rot_frames,
            scale_frames,
        ]

    return motion_data

def import_action(motion, armature, motion_name, bind_pose, rotation_resample=False):
    """apply motion data to armature"""
    action = bpy.data.actions.new(name=motion_name)
    # force Blender to save even if it has no users
    action.use_fake_user = True
    # a hint about which armature this action should be applied to
    action.target_user = armature.name
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    # This dictionary maps 'bone_id' to 'bone_name'.
    # In DMC4SE, bone_name is made up as "Bone" + str(bone_index), so 'bone_mapping' acts just
    # like a 'bone_id' to 'bone_index' mapping.
    #
    # When artists create an animation, a set of bones is used. When artists create a model,
    # another set of bones is used. If these two sets of bones match perfectly, you don't
    # have a problem of applying animations.
    # What if the two sets of bones don't match? Instead of fail to apply animations, you probably
    # want the animations to be 'partially applied'. For example, the animation is created for
    # a bone set with bones for extra addons, such as tail, cloak, etc, while the model uses
    # a skeletal without those bones, you might want that the animation for the body part can
    # be applied correctly. So, there must be a way to tell which bone matches which. That's why
    # a unique 'bone_id' is used, it makes sharing animations between models much easier.
    #
    bone_mapping = armature["bone_mapping"]
    pose_bones = armature.pose.bones
    # pose_bones = armature.data.bones

    print('[Info] armature.name: %s' % (armature.name))
    print('[Info] armature.data.name: %s' % (armature.data.name))

    # print('[Info]write motion to %s' % (str(type(pose_bones))))

    # print('current pose_bones:')
    # for k, v in pose_bones.items():
    #     print('%s --> %s' % (k, str(type(v))))

    used_bones = []

    for bone_number, v in motion.items():
        loc, rot, scale = v
        bone_name = bone_mapping.get(str(bone_number))

        if bone_name is None:
            print('[Error] bone_number = %d not found in bone_mapping.' % (bone_number))
            continue
        # pose_bone = pose_bones[bone_name]
        pose_bone = pose_bones.get(bone_name)
        if pose_bone is None:
            print('[Error] %s not found in armature.pose.bones.' % (bone_name))
            continue

        # Debug
        if bone_name not in used_bones:
            used_bones.append(bone_name);

        # location keyframes
        if loc is not None:
            for loc_k in loc:
                f = loc_k[0] + 1
                pose_bone.location = mathutils.Vector(loc_k[1:4])
                pose_bone.location -= bind_pose[bone_name][0]
                pose_bone.keyframe_insert("location", index=-1, frame=f)
        else:
            pose_bone.location = mathutils.Vector([0, 0, 0])
            pose_bone.keyframe_insert("location", index=-1, frame=1)
        # rotation keyframes
        if rot is not None:
            prev_f = 1
            for rot_k in rot:
                f = rot_k[0] + 1
                # In blender, quaternion is stored in order of w, x, y, z
                q = mathutils.Quaternion(
                    [rot_k[4], rot_k[1], rot_k[2], rot_k[3]]
                )
                q = bind_pose[bone_name][1].inverted() * q
                if f - prev_f > 1 and rotation_resample:
                    prev_q = mathutils.Quaternion(pose_bone.rotation_quaternion)
                    step = 1.0 / (f - prev_f)
                    fraction = 0.0
                    for i in range(f - prev_f):
                        fraction += step
                        _q = prev_q.slerp(q, fraction)
                        pose_bone.rotation_quaternion = _q
                        pose_bone.keyframe_insert(
                            "rotation_quaternion", index=-1, frame=prev_f + i + 1)
                else:
                    pose_bone.rotation_quaternion = q
                    pose_bone.keyframe_insert("rotation_quaternion", index=-1, frame=f)
                prev_f = f
        else:
            pose_bone.rotation_quaternion = mathutils.Quaternion([1, 0, 0, 0])
            pose_bone.keyframe_insert("rotation_quaternion", index=-1, frame=1)
        # scale keyframes
        if scale is not None:
            for scale_k in scale:
                f = scale_k[0] + 1
                pose_bone.scale = mathutils.Vector(scale_k[1:4])
                pose_bone.scale.x /= bind_pose[bone_name][2].x
                pose_bone.scale.y /= bind_pose[bone_name][2].y
                pose_bone.scale.z /= bind_pose[bone_name][2].z
                pose_bone.keyframe_insert("scale", index=-1, frame=f)
        else:
            pose_bone.scale = mathutils.Vector([1, 1, 1])
            pose_bone.keyframe_insert("scale", index=-1, frame=1)

    print('[Info] motion used bones:')
    debuginfo = ''
    for boneN in used_bones:
        debuginfo += boneN + ', '
    print(debuginfo)

    # force linear interpolation now
    for fcurve in action.fcurves:
        for keyframe_point in fcurve.keyframe_points:
            keyframe_point.interpolation = 'LINEAR'

def align4(size):
    """align to 4 bytes"""
    rem = size % 4
    if rem:
        size += 4 - rem
    return size

# something may be wrong
# def euler2Rotation(roll, pitch, yaw):
#     yawMatrix = numpy.matrix([
#             [math.cos(yaw), -math.sin(yaw), 0],
#             [math.sin(yaw), math.cos(yaw), 0],
#             [0, 0, 1]
#         ])
#     yawMatrix = numpy.matrix([
#             [math.cos(yaw), -math.sin(yaw), 0],
#             [math.sin(yaw), math.cos(yaw), 0],
#             [0, 0, 1]
#         ])
#     pitchMatrix = numpy.matrix([
#             [math.cos(pitch), 0, math.sin(pitch)],
#             [0, 1, 0],
#             [-math.sin(pitch), 0, math.cos(pitch)]
#         ])
#     rollMatrix = numpy.matrix([
#             [1, 0, 0],
#             [0, math.cos(roll), -math.sin(roll)],
#             [0, math.sin(roll), math.cos(roll)]
#         ])

#     R = yawMatrix * pitchMatrix * rollMatrix
#     theta = math.acos(((R[0, 0] + R[1, 1] + R[2, 2]) - 1) / 2)
#     multi = 0
#     if theta != 0:
#         multi = 1 / (2 * math.sin(theta))

#     rx = multi * (R[2, 1] - R[1, 2]) * theta
#     ry = multi * (R[0, 2] - R[2, 0]) * theta
#     rz = multi * (R[1, 0] - R[0, 1]) * theta

#     # print('input: %f,%f,%f' % (roll, pitch, yaw))
#     # print('out: %f,%f,%f' % (rx, ry, rz))

#     return rx, ry, rz, 1

def euler_angle_to_quaternion(roll, pitch, yaw):
    cy  =  math.cos(yaw * 0.5)
    sy  =  math.sin(yaw * 0.5)
    cr  =  math.cos(roll * 0.5)
    sr  =  math.sin(roll * 0.5)
    cp  =  math.cos(pitch * 0.5)
    sp  =  math.sin(pitch * 0.5)

    w  =  cy  *  cr  *  cp  +  sy  *  sr  *  sp
    x  =  cy  *  sr  *  cp  -  sy  *  cr  *  sp
    y  =  cy  *  cr  *  sp  +  sy  *  sr  *  cp
    z  =  sy  *  cr *  cp  -  cy  *  sr  *  sp

    return x, y, z, w

def quaternion_to_euler_angle(w, x, y, z):
    ysqr = y * y
    
    t0 = +2.0 * (w * x + y * z)
    t1 = +1.0 - 2.0 * (x * x + ysqr)
    X = math.degrees(math.atan2(t0, t1))
    
    t2 = +2.0 * (w * y - z * x)
    t2 = +1.0 if t2 > +1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    Y = math.degrees(math.asin(t2))
    
    t3 = +2.0 * (w * z + x * y)
    t4 = +1.0 - 2.0 * (ysqr + z * z)
    Z = math.degrees(math.atan2(t3, t4))
    
    return X, Y, Z

def calc_bind_pose_transforma(armature):
    m = mathutils.Matrix()
    m[0].xyzw = 1, 0, 0, 0
    m[1].xyzw = 0, 0, 1, 0
    m[2].xyzw = 0, -1, 0, 0
    m[3].xyzw = 0, 0, 0, 1

    # TODO:骨骼p,r,s数据计算可能不正确
    bind_pose = {}
    for bone in armature.data.edit_bones:
        # print('calc %s' % (bone.name))
        if bone.parent is None:
            loc_mat = m * bone.matrix
        else:
            loc_mat = (m * bone.parent.matrix).inverted() * (m * bone.matrix)
        loc, rot, scale = loc_mat.decompose()
        bind_pose[bone.name] = (loc, rot, scale)
    return bind_pose

def main(mot_file, armature):
    fp = open(mot_file, "rb")
    motReader = MOT.get_getter(fp, "<")
    
    assert motReader.get("4s") == SIGN

    version = motReader.get("I")
    assert version == 0x20120405

    unk0 = motReader.get("H")
    frame_count = motReader.get("H")
    track_offset = motReader.get("I")
    track_count = motReader.get("I")
    unk1 = motReader.get("I")
    name = motReader.get("20s").decode('utf8').rstrip("\x00")
    
    print ("MOT header: 0x%x, %d, name=%s, frame=%d" %
           (unk0, unk1, name, frame_count))

    tracks = read_track(motReader, track_offset, track_count)
    motion_data = read_motionData(frame_count, tracks)

    bpy.ops.object.mode_set(mode='EDIT')
    bind_pose = calc_bind_pose_transforma(armature)
    bpy.ops.object.mode_set()

    import_action(motion_data, armature, name, bind_pose)

    fp.close()
    return {'FINISHED'}

if __name__ == '__main__':
    main('', None)
