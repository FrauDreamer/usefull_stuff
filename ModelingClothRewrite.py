



import bpy
from bpy.ops import op_as_string
from bpy.app.handlers import persistent
import os
import bmesh
import functools as funky
import numpy as np
from numpy import newaxis as nax
import time
import copy # for duplicate cloth objects

# global data
MC_data = {}
MC_data['colliders'] = {}
MC_data['cloths'] = {}
MC_data['iterator'] = 0

# recent_object allows cloth object in ui
#   when selecting empties such as for pinning.
MC_data['recent_object'] = None


def reload():
    """!! for development !! Resets everything"""
    # when this is registered as an addon I will want
    #   to recaluclate these objects not set prop to false
    
    # Set all props to False:
    reload_props = ['continuous', 'collider', 'animated', 'cloth']
    if 'MC_props' in dir(bpy.types.Object):
        for i in reload_props:
            for ob in bpy.data.objects:
                ob.MC_props[i] = False

    for i in bpy.data.objects:
        if "MC_cloth_id" in i:
            del(i["MC_cloth_id"])
        if "MC_collider_id" in i:
            del(i["MC_collider_id"])

    #for detecting deleted colliders or cloths
    MC_data['cloth_count'] = 0
    MC_data['collider_count'] = 0


reload()


print("new--------------------------------------")
def cache(ob):
    # for when I cache animation data
    # store the cache in the place where
    # the blend file is saved
    # if the blend file is not saved should
    #   prolly store it in a tmp directors...
    folder = bpy.data.filepath
    file = os.path.join(folder, ob.name)


# debugging
def T(type=1, message=''):
    if type == 1:
        return time.time()
    print(time.time() - type, message)


# ============================================================ #
#                    universal functions                       #
#                                                              #

def get_normals_from_tris(tris):
    origins = tris[:, 0]
    vecs = tris[:, 1:] - origins[:, nax]
    cross = np.cross(vecs[:, 0], vecs[:, 1])
    mag = np.sqrt(np.einsum("ij ,ij->i", cross, cross))[:, nax]
    return np.nan_to_num(cross/mag)    


def cross_from_tris(tris):
    origins = tris[:, 0]
    vecs = tris[:, 1:] - origins[:, nax]
    cross = np.cross(vecs[:, 0], vecs[:, 1])
    return cross
    

def apply_rotation(object, normals):
    """When applying vectors such as normals we only need
    to rotate"""
    m = np.array(object.matrix_world)
    mat = m[:3, :3].T
    #object.v_normals = object.v_normals @ mat
    return normals @ mat
    
    
def revert_rotation(ob, co):
    """When reverting vectors such as normals we only need
    to rotate"""
    m = np.array(ob.matrix_world)
    mat = m[:3, :3] # rotates backwards without T
    return co @ mat


def revert_transforms(ob, co):
    """Set world coords on object. 
    Run before setting coords to deal with object transforms
    if using apply_transforms()"""
    m = np.linalg.inv(ob.matrix_world)    
    mat = m[:3, :3]# rotates backwards without T
    loc = m[:3, 3]
    return co @ mat + loc  


def revert_in_place(ob, co):
    """Revert world coords to object coords in place."""
    m = np.linalg.inv(ob.matrix_world)    
    mat = m[:3, :3]# rotates backwards without T
    loc = m[:3, 3]
    co[:] = co @ mat + loc


def apply_in_place(ob, arr):
    """Overwrite vert coords in world space"""
    m = np.array(ob.matrix_world, dtype=np.float32)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    arr[:] = arr @ mat + loc
    return arr


def apply_transforms(ob, co):
    """Get vert coords in world space"""
    m = np.array(ob.matrix_world, dtype=np.float32)    
    mat = m[:3, :3].T # rotates backwards without T
    loc = m[:3, 3]
    return co @ mat + loc


def copy_object_transforms(ob1, ob2):
    M = ob1.matrix_world.copy()
    ob2.matrix_world = M


def manage_locations_as_strings(old, new):
    # vertex coords for each point in old to a key as string
    """ !!! not finished !!! """
    idx_co_key = {}
    vs = ob.data.vertices
    flat_faces = np.hstack(sel_faces)
    for i in range(len(flat_faces)):
        idx_co_key[str(vs[flat_faces[i]].co)] = flat_faces[i]


def offset_face_indices(faces=[]):
    """Sorts the original face vert indices
    for a new mesh from subset. Works with N-gons"""
    # Example: face_verts = [[20, 10, 30], [10, 30, 100, 105]]
    # Converts to [[1, 0, 2], [0, 2, 3, 4]]

    def add(c):
        c['a'] += 1
        return c['a']

    flat = np.hstack(faces)
    idx = np.unique(flat, return_inverse=True)[1]
    c = {'a': -1}
    new_idx = [[idx[add(c)] for j in i] for i in faces]
    return new_idx
    

# universal ---------------
def link_mesh(verts, edges, faces, name='name'):
    """Generate and link a new object from pydata"""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, faces)  
    mesh.update()
    mesh_ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(mesh_ob)
    return mesh_ob
    

# universal ---------------
def mesh_from_selection(ob, name='name'):
    """Generate a new mesh from selected faces"""
    obm = get_bmesh(ob)
    obm.faces.ensure_lookup_table()
    faces = [[v.index for v in f.verts] for f in obm.faces if f.select]
    if len(faces) == 0:
        print("No selected faces in mesh_from_selection")
        return # no faces
    
    obm.verts.ensure_lookup_table()
    verts = [i.co for i in obm.verts if i.select]        
    idx_faces = offset_face_indices(faces)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], idx_faces)  
    mesh.update()
    if False:    
        mesh_ob = ob.copy()
    else:
        mesh_ob = bpy.data.objects.new(name, mesh)
    
    mesh_ob.data = mesh
    mesh_ob.name = name
    bpy.context.collection.objects.link(mesh_ob)    
    return mesh_ob, faces, idx_faces        


# universal ---------------
def co_overwrite(ob, ar):
    """Fast way to overwite"""
    shape = ar.shape
    ar.shape = (shape[0] * 3,)
    ob.data.vertices.foreach_get('co', ar)
    ar.shape = shape


# universal ---------------
def get_bmesh(ob=None):
    if ob.data.is_editmode:
        return bmesh.from_edit_mesh(ob.data)
    obm = bmesh.new()
    obm.from_mesh(ob.data)    
    return obm


# universal ---------------
def get_co(ob, ar=None):
    """Get vertex coordinates from an object in object mode"""
    if ar is None:
        v_count = len(ob.data.vertices)
        ar = np.empty(v_count * 3, dtype=np.float32)
    ar.shape = (v_count * 3,)
    ob.data.vertices.foreach_get('co', ar)
    ar.shape = (v_count, 3)
    return ar


# universal ---------------
def get_co_shape(ob, key=None, ar=None):
    """Get vertex coords from a shape key"""
    v_count = len(ob.data.shape_keys.key_blocks[key].data)
    if ar is None:
        ar = np.empty(v_count * 3, dtype=np.float32)
    ob.data.shape_keys.key_blocks[key].data.foreach_get('co', ar)
    ar.shape = (v_count, 3)
    return ar


# universal ---------------
def get_co_edit(ob, obm=None):
    """Get vertex coordinates from an object in edit mode"""
    if obm is None:
        obm = get_bmesh(ob)
        obm.verts.ensure_lookup_table()
    co = np.array([i.co for i in obm.verts])
    return co


# universal ---------------
def Nx3(ob):
    """For generating a 3d vector array"""
    if ob.data.is_editmode:
        obm = bmesh.from_edit_mesh(ob.data)
        obm.verts.ensure_lookup_table()
        count = (len(obm.verts))
    else:
        count = len(ob.data.vertices)
    ar = np.zeros(count*3, dtype=np.float32)
    ar.shape = (count, 3)
    return ar

# universal ---------------
def get_co_mode_2(ob, arr):
    ob.update_from_editmode()
    ob.data.vertices.foreach_get('co', arr.ravel())
    return arr


# universal ---------------
def get_co_mode(ob=None):
    """Edit or object mode"""
    if ob is None: # cloth.target object might be None
        return None
    if ob.data.is_editmode:
        obm = bmesh.from_edit_mesh(ob.data)
        obm.verts.ensure_lookup_table()
        co = np.array([i.co for i in obm.verts], dtype=np.float32)
        return co

    count = len(ob.data.vertices)
    ar = np.zeros(count*3, dtype=np.float32)
    ob.data.vertices.foreach_get('co', ar)
    ar.shape = (count, 3)
    return ar


# universal ---------------
def compare_geometry(ob1, ob2, obm1=None, obm2=None, all=False):
    """Check for differences in verts, edges, and faces between two objects"""
    # if all is false we're comparing a target objects. verts in faces
    #   and faces must match.
    def get_counts(obm):
        v_count = len([v for v in obm.verts if len(v.link_faces) > 0])
        #v_count = len(obm.verts) # not sure if I need to separate verts...
        e_count = len(obm.edges)
        f_count = len(obm.faces)
        if all:
            return np.array([v_count, e_count, f_count])
        return np.array([v_count, f_count]) # we can still add sew edges in theory...

    if obm1 is None:
        obm1 = get_bmesh(ob1)
    if obm2 is None:
        obm2 = get_bmesh(ob2)

    c1 = get_counts(obm1)
    c2 = get_counts(obm2)

    return np.all(c1 == c2)


# universal ---------------
def detect_changes(counts, obm):
    """Compare mesh data to detect changes in edit mode"""
    # counts in an np array shape (3,)
    v_count = len(obm.verts)
    e_count = len(obm.edges)
    f_count = len(obm.faces)
    new_counts = np.array([v_count, e_count, f_count])
    # Return True if all are the same
    return np.all(counts == new_counts), f_count < 1


# universal ---------------
def get_mesh_counts(ob, obm=None):
    """Returns information about object mesh in edit or object mode"""
    if obm is not None:
        v_count = len(obm.verts)
        e_count = len(obm.edges)
        f_count = len(obm.faces)
        return np.array([v_count, e_count, f_count])
    v_count = len(ob.data.vertices)
    e_count = len(ob.data.edges)
    f_count = len(ob.data.polygons)
    return np.array([v_count, e_count, f_count])


# universal ---------------
def reset_shapes(ob):
    """Create shape keys if they are missing"""

    if ob.data.shape_keys == None:
        ob.shape_key_add(name='Basis')
    
    keys = ob.data.shape_keys.key_blocks    
    if 'MC_source' not in keys:
        ob.shape_key_add(name='MC_source')
        keys['MC_source'].value=1
    
    if 'MC_current' not in keys:
        ob.shape_key_add(name='MC_current')
        keys['MC_current'].value=1
        keys['MC_current'].relative_key = keys['MC_source']
        

# universal ---------------
def get_weights(ob, name, obm=None):
    """Get vertex weights. If no weight is assigned assign
    and set weight to zero"""
    # might want to look into using map()
    count = len(ob.data.vertices)

    g_idx = ob.vertex_groups[name].index

    # for edit mode:
    if ob.data.is_editmode:
        count = len(obm.verts)
        arr = np.zeros(count, dtype=np.float32)
        dvert_lay = obm.verts.layers.deform.active
        if dvert_lay is None: # if there are no assigned weights
            return arr
        for idx, v in enumerate(obm.verts):
            dvert = v[dvert_lay]

            if g_idx in dvert:
                arr[idx] = dvert[g_idx]
            else:
                dvert[g_idx] = 0
                arr[idx] = 0
        return arr

    arr = np.zeros(count, dtype=np.float32)

    g = ob.vertex_groups[name]
    for idx, v in enumerate(ob.data.vertices):
        try:
            w = g.weight(idx)
            arr[idx] = w
        except RuntimeError:
            # Raised when the vertex is not part of the group
            w = 0
            ob.vertex_groups[name].add([g_idx, idx], w, 'REPLACE')
            arr[idx] = w

    return arr


# universal ---------------
def slice_springs(idx, co):
    pass
    
    
def bend_springs():
    #is there a way to get bend relationships from 
    #just the basis springs...
    #Or could I do something like virtual springs
    #but for bend sets...
    pass    


def box_bary_weights(poly, point, vals=[]):
    """Get values to plot points from tris
    or return the new plotted value."""
    # note: could use a lot of add.at/subtract.at and
    #   obscenely complex indexing to do bend springs
    #   between n-gons. It would be a riot!
    print(poly[:,2])
    if vals: # two scalar values
        ba = poly[1] - poly[0]
        ca = poly[2] - poly[0]
        v1, v2 = vals[0], vals[1]
        plot = poly[0] + (((ba * v1) + (ca * v2)) * .5)
        #plot = poly[0]# + (((ba * v1) + (ca * v2)) * .5)
        print(v1, v2, " v1 and v2 ")
        return plot

    pa = point - poly[0]
    ba = poly[1] - poly[0]
    ca = poly[2] - poly[0]
    
    print(pa, ba, "pa and ba")
    v1 = np.nan_to_num(pa / ba)
    v2 = np.nan_to_num(pa / ca)
    print(v1[2],v2[2])
    return [v1, v2]


# universal ---------------
def inside_triangles(tris, points, check=True, surface_offset=False, cloth=None):
    """Can check inside triangle.
    Can find barycentric weights for triangles.
    Can find multiplier for distance off surface
        from non-unit cross product."""
    origins = tris[:, 0]
    cross_vecs = tris[:, 1:] - origins[:, nax]    
    v2 = points - origins

    # ---------
    v0 = cross_vecs[:,0]
    v1 = cross_vecs[:,1]
    
    d00_d11 = np.einsum('ijk,ijk->ij', cross_vecs, cross_vecs)
    d00 = d00_d11[:,0]
    d11 = d00_d11[:,1]
    d01 = np.einsum('ij,ij->i', v0, v1)
    d02 = np.einsum('ij,ij->i', v0, v2)
    d12 = np.einsum('ij,ij->i', v1, v2)

    div = 1 / (d00 * d11 - d01 * d01)
    u = (d11 * d02 - d01 * d12) * div
    v = (d00 * d12 - d01 * d02) * div
    
    weights = np.array([1 - (u+v), u, v, ]).T
    if not check | surface_offset:
        return weights
    
    if not check:
        cross = np.cross(cross_vecs[:,0], cross_vecs[:,1])
        d_v2_c = np.einsum('ij,ij->i', v2, cross)
        d_v2_v2 = np.einsum('ij,ij->i', cross, cross) 
        div = d_v2_c / d_v2_v2        

        U_cross = cross / np.sqrt(d_v2_v2)[:, None]
        U_d = np.einsum('ij,ij->i', v2, U_cross)
        
        
        return weights, div, U_d# for normalized
    
    check = np.all(weights > 0, axis=0)
    # check if bitwise is faster when using lots of tris
    if False:    
        check = (u > 0) & (v > 0) & (u + v < 1)

    return weights.T, check


def cpoe_bend_plot_values(cloth):

    # get axis vecs
    co = get_co_shape(cloth.ob, key="MC_source")
    be = cloth.bend_edges
    tt = cloth.bend_tri_tips.reshape(be.shape)   #[:, ::-1] # flip it to the other side
    po_vecs = co[tt] - co[be[:, 0]][:, None]
    tris = co[tt]
    origins = co[be[:, 0]]
    
    # get axis plot (non-unit vecs so it will scale? I think this makes sense...)
    axis_vecs = co[be[:, 1]] - origins
    d_po = np.einsum('ij, ikj->ik', axis_vecs, po_vecs)
    d_axis = np.einsum('ij,ij->i', axis_vecs, axis_vecs)
    # --------------------------------------
    cloth.axis_div = d_po / d_axis[:, None]
    """
    A pair of axis dots for each axis. One for each tri tip, and a partridge in a pair tree.
    """
    
    # get cross plot (unit vecs here stabilize)
    cross_vecs = tris - origins[:, None]
    cross = np.roll(np.cross(cross_vecs, axis_vecs[:, None]), 1, axis=1)
    n_2_3 = cross.shape
    n_3 = (n_2_3[0] *2, 3)
    cross.shape = n_3
    po_vecs.shape = cross.shape
    U_cross = cross / np.sqrt(np.einsum('ij, ij->i', cross, cross))[:, None]
    # --------------------------------------
    cloth.cross_div = np.einsum('ij, ij->i', U_cross, po_vecs)[:, None]

    """
    How far off the surface the opposite tri tip is along the normal
    """
    
    # get tri plot (unit vecs here stabilize)
    cross.shape = n_2_3
    tri_vecs = np.cross(cross, axis_vecs[:, None])
    tri_vecs.shape = n_3
    cross.shape = n_3
    d_tv = np.einsum('ij, ij->i', tri_vecs, tri_vecs)
    U_tri = tri_vecs / np.sqrt(d_tv)[:, None] 
    # --------------------------------------
    cloth.tri_div = np.einsum('ij, ij->i', U_tri, po_vecs)[:, None]
    """
    Cross of the normal and the axis pointing perpindicular to the axis
    along the surface of the tri opposite the tip.
    """


def cpoe_bend_plot(cloth):
    """Plot values based on cpoe using axis and cross products"""
    
    axis_div = cloth.axis_div
    tri_div = cloth.tri_div
    cross_div = cloth.cross_div
    
    co = cloth.co
    be = cloth.bend_edges
    tt = cloth.bend_tri_tips.reshape(be.shape)   #[:, ::-1] # flip it to the other side
    po_vecs = co[tt] - co[be[:, 0]][:, None]
    tris = co[tt]
    origins = co[be[:, 0]]

    # plot axis (origin added here)
    axis_vecs = co[be[:, 1]] - origins
    axis_plot = origins[:, None] + axis_vecs[:, None] * axis_div[:,:,None]

    # plot normal
    cross_vecs = tris - origins[:, None]
    cross = np.roll(np.cross(cross_vecs, axis_vecs[:, None]), 1, axis=1)
    n_2_3 = cross.shape
    n_3 = (n_2_3[0] * 2, 3)
    cross.shape = n_3
    po_vecs.shape = cross.shape
    U_cross = cross / np.sqrt(np.einsum('ij, ij->i', cross, cross))[:, None]
    cross_plot = U_cross * cross_div
    

    # plot along tri surface
    cross.shape = n_2_3
    tri_vecs = np.cross(cross, axis_vecs[:, None])
    tri_vecs.shape = n_3
    cross.shape = n_3
    d_tv = np.einsum('ij, ij->i', tri_vecs, tri_vecs)
    U_tri = tri_vecs / np.sqrt(d_tv)[:, None] 
    tri_plot = U_tri * tri_div

    axis_plot.shape = n_3
    plot = tri_plot + axis_plot + cross_plot
    
    return plot
    

def get_cloth(ob):
    """Return the cloth instance from the object"""    
    return MC_data['cloths'][ob['MC_cloth_id']]

# ^                                                          ^ #
# ^                 END universal functions                  ^ #
# ============================================================ #




# ============================================================ #
#                   precalculated data                         #
#                                                              #

# precalculated ---------------
def closest_point_mesh(obm, ob, idx, target):
    """Uses bmesh method to get CPM"""
    context = bpy.context
    scene = context.scene
    
    obm.verts.ensure_lookup_table()
    tmwi = target.matrix_world.inverted()

    locs = []
    faces = []
    norms = []
    cos = []
    for i in idx:    
        co = ob.matrix_world @ obm.verts[i].co # global face median
        #co = obm.verts[i].co # global face median
        cos.append(co)
        local_pos = tmwi @ co  # face cent in target local space

        (hit, loc, norm, face_index) = target.closest_point_on_mesh(local_pos)
        #print(hit, loc, norm, face_index)
        if hit:
            #locs.append(target.matrix_world @ loc)
            locs.append(loc)
            faces.append(face_index)
            norms.append(norm)
            empties = True
            empties = False
            if empties:    
                bpy.ops.object.empty_add(location=target.matrix_world @ loc)

    print("need to create dtypes for these array below")
    return np.array(locs), np.array(faces), np.array(norms), np.array(cos)


def get_tridex(ob, tobm=None):
    """Return an index for viewing the verts as triangles"""
    free = False
    if tobm is None:
        tobm = bmesh.new()
        tobm.from_mesh(ob.data)
        free = True
    bmesh.ops.triangulate(tobm, faces=tobm.faces[:])
    tridex = np.array([[v.index for v in f.verts] for f in tobm.faces], dtype=np.int32)
    if free:    
        tobm.free()
    return tridex


def get_tridex_2(ob): # faster than get_tridex()
    """Return an index for viewing the
    verts as triangles using a mesh and
    foreach_get""" 
    if ob.data.is_editmode:    
        ob.update_from_editmode()
    tobm = bmesh.new()
    tobm.from_mesh(ob.data)
    bmesh.ops.triangulate(tobm, faces=tobm.faces[:])
    me = bpy.data.meshes.new('tris')
    tobm.to_mesh(me)
    p_count = len(me.polygons)
    tridex = np.empty(p_count * 3, dtype=np.int32)
    me.polygons.foreach_get('vertices', tridex)
    tridex.shape = (p_count, 3)    
    
    # clear unused tri mesh
    bpy.data.meshes.remove(me)
    
    return tridex, tobm


def get_bend_sets(cloth):
    """Each edge with two faces makes a bend edge.
    The mesh is triangluated so the tip of each triangle
    whose base is the edge is moved like a hinge
    around the bend edge."""
    
    ob = cloth.ob
    tridex, obm = get_tridex_2(ob)
    obm.edges.ensure_lookup_table()
    T = time.time()
    bend_data = np.array([[e.verts[0].index, e.verts[1].index, e.index] for e in obm.edges if len(e.link_faces) == 2], dtype=np.int32)
    if bend_data.shape[0] == 0:
        cloth.bend_data = None
        return
    bend_edges = bend_data[:, :2]
    ed_idx = bend_data[:, -1:].ravel()    

    lf = [obm.edges[e].link_faces for e in ed_idx]
    fidx = np.array([[i[0].index, i[1].index] for i in lf])
    
    c = tridex[fidx.ravel()]
    a = bend_edges.ravel()[:, None]
    b = bend_edges[:, ::-1].ravel()[:, None]
    
    bool1 = a == c
    bool2 = b == c
    
    tri_tips = c[~(bool1 | bool2)]
    # switch tri_tips so the tip pairs with the tri
    #   on the opposite side of the edge.
    shape = tri_tips.shape
    tri_tips.shape = (shape[0]//2, 2)
    tri_tips = tri_tips[:,::-1].ravel()

    # write to class instance
    cloth.tridex = tridex
    cloth.bend_ed_idx = ed_idx
    cloth.bend_edges = bend_edges
    cloth.bend_tri_tips = tri_tips
    cloth.bend_tris = c
    obm.free()

    # can be dynamic
    bary_bend_springs(cloth)
    cloth.bend_tri_tip_array = np.zeros(len(cloth.ob.data.vertices), dtype=np.float32)#[:, None]


def bary_bend_springs(cloth):
    """Dynamic portion of bend springs
    (as opposed to index groups)"""
    co = get_co_shape(cloth.ob, key='MC_source')
    tris = co[cloth.bend_tris]
    points = co[cloth.bend_tri_tips]
    weights, surface_offset, U_d = inside_triangles(tris, points, check=False, surface_offset=True, cloth=cloth)
    cloth.bend_weights = weights[:,:,None]
    cloth.bend_surface_offset = surface_offset[:, None]
    cloth.bend_U_d = U_d
    

# precalculated ---------------
def create_surface_follow_data(active, cloths):
    """Need to run this every time
    we detect 'not same' """
    
    # !!! need to make a global dg shared between cloth objects???
    selection = active.MC_props.surface_follow_selection_only
    
    for c in cloths:
        cloth = MC_data['cloths'][c['MC_cloth_id']]
        proxy = active.evaluated_get(cloth.dg)
        cloth.surface = True
        cloth.surface_object = proxy
            
        # temp -------------------------------------------
        #mesh_ob = proxy.copy()
        #bpy.context.collection.objects.link(mesh_ob)              
        #mesh_ob.data.update()
        # temp -------------------------------------------         
        
        cloth.surface_object = proxy        
        vw = get_weights(c, 'MC_surface_follow', obm=cloth.obm)
        idx = np.where(vw != 0)[0]
        cloth.bind_idx = idx
        
        print("have to run the surface calculations when updating groups")
        
        if selection:
            sel_object, sel_faces, idx_faces = mesh_from_selection(proxy, "temp_delete_me")        
            if sel_object is None:
                return 'Select part of the mesh or turn off "Selection Only"'
            
            # triangulate selection object mesh for barycentric weights
            sel_obm = bmesh.new()
            sel_obm.from_mesh(sel_object.data)
            bmesh.ops.triangulate(sel_obm, faces=sel_obm.faces[:])
            sel_obm.to_mesh(sel_object.data)
            sel_object.data.update()
            copy_object_transforms(proxy, sel_object)
            sel_tridex = get_tridex(sel_object, sel_obm)
            sel_obm.free()
            
            # find barycentric data from selection mesh
            locs, faces, norms, cos = closest_point_mesh(cloth.obm, c, idx, sel_object)
            
            # converts coords to dict keys so we can find corresponding verts in surface follow mesh
            idx_co_key = {}
            pvs = proxy.data.vertices
            flat_faces = np.hstack(sel_faces)
            for i in range(len(flat_faces)):
                idx_co_key[str(pvs[flat_faces[i]].co)] = flat_faces[i]
            
            # use keys to get correspoinding vertex indices                    
            flat_2 = np.hstack(sel_tridex[faces])
            co_key_2 = []
            vs = sel_object.data.vertices
            tri_keys = [str(vs[i].co) for i in flat_2]
            surface_follow_tridex = [idx_co_key[i] for i in tri_keys]
            
            # convert to numpy and reshape            
            cloth.surface_tridex = np.array(surface_follow_tridex)

            cloth.surface_tris_co = np.array([pvs[i].co for i in cloth.surface_tridex], dtype=np.float32)
            shape = cloth.surface_tridex.shape[0]
            cloth.surface_tridex.shape = (shape // 3, 3)
            cloth.surface_tris_co.shape = (shape // 3, 3, 3)
            #v = proxy.data.vertices
            #for i in cloth.surface_tridex.ravel():
                #bpy.ops.object.empty_add(location=proxy.matrix_world @ v[i].co)
            #print(tri_keys)
                    
            # delete temp mesh        
            me = sel_object.data    
            bpy.data.objects.remove(sel_object)
            bpy.data.meshes.remove(me)
            
            # generate barycentric weights            
            cloth.surface_bary_weights = inside_triangles(cloth.surface_tris_co, locs, check=False)
            

            dif = cos - apply_transforms(active, locs)
            #cloth.surface_norms = norms
            cloth.surface_norm_vals = np.sqrt(np.einsum("ij ,ij->i", dif, dif))[:, nax]
            print(cloth.surface_norm_vals, "this guy!!!!!!!!")
            # Critical values for barycentric placement:
            #   1: cloth.surface_tridex          (index of tris in surface object)
            #   2: cloth.surface_bary_weights    (barycentric weights)
            #   3: cloth.surface_object          (object we're following)
            #   4: cloth.surface                 (bool value indicating we should run surface code)
            #   5: cloth.bind_idx = idx          (verts that are bound to the surface)
            #   6: cloth.surface_norms = norms   (direction off surface of tris)
            #   7: cloth.surface_normals = norms (mag of surface norms)

# precalculated ---------------
def eliminate_duplicate_pairs(ar):
    # Not currently used...
    """Eliminates duplicates and mirror duplicates.
    for example, [1,4], [4,1] or duplicate occurrences of [1,4]
    Returns an Nx2 array."""
    # no idea how this works (probably sorcery) but it's really fast
    a = np.sort(ar, axis=1)
    x = np.random.rand(a.shape[1])
    y = a @ x
    unique, index = np.unique(y, return_index=True)
    return a[index]


def virtual_springs(cloth):
    """Adds spring sets checking if springs
    are already present using strings.
    Also stores the set so we can check it
    if there are changes in geometry."""
    
    # when we detect changes in geometry we
    #   regenerate the springs, then add 
    #   cloth.virtual_springs to the basic
    #   array after we check that all the
    #   verts in the virtual springs are
    #   still in the mesh.
    verts = cloth.virtual_spring_verts
    ed = cloth.basic_set
        
    string_spring = [str(e[0]) + str(e[1]) for e in ed]
    
    strings = []
    new_ed = []
    for v in verts:
        for j in verts:
            if j != v:
                stringy = str(v) + str(j)
                strings.append(stringy)
                #if stringy not in string_spring:
                new_ed.append([v,j])
    
    in1d = np.in1d(strings, string_spring)
    cull_ed = np.array(new_ed)[~in1d]    
    cloth.virtual_springs = cull_ed # store it for checking when changing geometry
    cloth.basic_set = np.append(cloth.basic_set, cull_ed, axis=0)
    cloth.basic_v_fancy = cloth.basic_set[:,0]
    # would be nice to have a mesh or ui magic to visualise virtual springs
    # !!! could do a fixed type sew spring the same way !!!
    # !!! maybe use a vertex group for fixed sewing? !!!
    # !!! Could also use a separate object for fixed sewing !!!
    
    
def get_springs_2(cloth):
    """Create index for viewing stretch springs"""
    obm = cloth.obm
    obm.verts.ensure_lookup_table()
    
    TT = time.time()
    ed = []
    for v in obm.verts:
        v_set = []
        for f in v.link_faces:
            for vj in f.verts:
                if vj != v:    
                    stri = str(v.index) + str(vj.index)
                    if stri not in v_set:    
                        ed.append([v.index, vj.index])
                        v_set.append(stri)
    
    cloth.basic_set = np.array(ed)
    cloth.basic_v_fancy = cloth.basic_set[:,0]
    


# precalculated ---------------
def get_springs(cloth, obm=None, debug=False):
    # Not currently used. Using get_springs_2
    """Creates minimum edges and indexing arrays for spring calculations"""
    if obm is None:
        obm = get_bmesh(cloth.ob)
    
    TT = time.time()
    # get index of verts related by polygons for each vert
    id = [[[v.index for v in f.verts if v != i] for f in i.link_faces] for i in obm.verts]

    # strip extra dimensions
    squeezed = [np.unique(np.hstack(i)) if len(i) > 0 else i for i in id]

    # create list pairing verts with connected springs
    paired = [[i, np.ones(len(i), dtype=np.int32)*r] for i, r in zip(squeezed, range(len(squeezed)))]

    # merge and cull disconnected verts
    merged1 = [np.append(i[0][nax], i[1][nax], axis=0) for i in paired if len(i[0]) > 0]
    a = np.hstack([i[0] for i in merged1])
    b = np.hstack([i[1] for i in merged1])
    final = np.append(a[nax],b[nax], axis=0).T
    
    springs = eliminate_duplicate_pairs(final)

    # generate indexers for add.at
    v_fancy, e_fancy, flip = b, [], []
    nums = np.arange(len(obm.verts)) # need verts in case there are disconnected verts in mesh
    idxer = np.arange(springs.shape[0] * 2)
    flat_springs = springs.T.ravel()
    mid = springs.shape[0]

    # would be nice to speed this up a bit...
    for i in nums:
        hit = idxer[i==flat_springs]
        if len(hit) > 0: # nums and idxer can be different because of disconnected verts
            for j in hit:
                if j < mid:
                    e_fancy.append(j)
                    flip.append(1)
                else:
                    e_fancy.append(j - mid)
                    flip.append(-1)

    #debug=True
    if debug:
        print('---------------------------------------------')
        for i, j, k, in zip(v_fancy, springs[e_fancy], flip):
            print(i,j,k)

    #print("created springs --------------------------------------")
    return springs, v_fancy, e_fancy, np.array(flip)[:, nax]


# ^                                                          ^ #
# ^                 END precalculated data                   ^ #
# ============================================================ #

# ============================================================ #
#                      cloth instance                          #
#                                                              #

# collider instance -----------------
class Collider(object):
    # The collider object
    pass


# collider instance -----------------
def create_collider():
    collider = Collider()
    collider.name = "Henry"
    collider.ob = bpy.context.object
    return collider


# cloth instance ---------------
class Cloth(object):
    # The cloth object
    pass


# cloth instance ---------------
def create_instance():
    """Run this when turning on modeling cloth."""
    cloth = Cloth()
    cloth.dg = bpy.context.evaluated_depsgraph_get()
    ob = bpy.context.object
    cloth.ob = ob
    
    if True:
        # testng ----------------
        # testng ----------------

        cloth.red = bpy.data.objects['red']
        cloth.green = bpy.data.objects['green']
        
        # testng ----------------
        # testng ----------------

    # check for groups:
    if 'MC_pin' not in ob.vertex_groups:
        ob.vertex_groups.new(name='MC_pin')

    # drag can be something like air friction
    if 'MC_drag' not in ob.vertex_groups:
        ob.vertex_groups.new(name='MC_drag')
    
    # surface follow
    if 'MC_surface_follow' not in ob.vertex_groups:
        ob.vertex_groups.new(name='MC_surface_follow')

    # stuff ---------------
    cloth.obm = get_bmesh(ob)
    cloth.pin = get_weights(ob, 'MC_pin', obm=cloth.obm)[:, nax]
    cloth.surface_vgroup_weights = get_weights(ob, 'MC_surface_follow', obm=cloth.obm)[:, nax]
    cloth.update_lookup = False
    cloth.selected = np.zeros(len(ob.data.vertices), dtype=np.bool)

    # surface follow data ------------------------------------------
    cloth.surface_tridex = None         # (index of tris in surface object)
    cloth.surface_bary_weights = None   # (barycentric weights)
    cloth.surface_object = None         # (object we are following)
    cloth.surface = False               # (bool value indicating we should run surface code)
    cloth.bind_idx = None               # (verts that are bound to the surface)
    
    if False:
        # Update groups (I think to create the vertex group arrays like cloth.pin, etc...)
        if ob.data.is_editmode:
            cloth.obm.verts.layers.deform.verify() # for vertex groups
            #cloth.obm.verts.layers.deform.new()
            update_groups(cloth, cloth.obm)
        else:
            update_groups(cloth)

    cloth.undo = False

    # the target for stretch and bend springs
    cloth.proxy = None
    cloth.target = None # (gets overwritten by def cb_target)
    cloth.target_obm = None
    cloth.target_undo = False
    cloth.target_geometry = None # (gets overwritten by cb_target)
    cloth.target_mode = 1
    if cloth.target is not None:
        if cloth.target.data.is_editmode:
            cloth.target_mode = None

    # for detecting changes in geometry
    cloth.geometry = get_mesh_counts(ob)

    # for detecting mode changes
    cloth.mode = 1
    if ob.data.is_editmode:
        cloth.mode = None

    #t = T()
    #cloth.springs, cloth.v_fancy, cloth.e_fancy, cloth.flip = get_springs(cloth)
    #T(t, "time it took to get the springs")

    t = T()
    get_springs_2(cloth)
    T(t, "time it took to get the springs")

    # coordinates and arrays ------------
    if ob.data.is_editmode:
        cloth.co = get_co_mode(ob)
    else:
        cloth.co = get_co_shape(ob, 'MC_current')


    # Bend spring data ()------------------
    cloth.bend_data = True            # gets overwritten as none if there no bend sets
    cloth.tridex = None               # index the whole cloth mesh as triangles
    cloth.bend_ed_idx = None          # index the edges that are bend axes
    cloth.bend_edges = None           # index the verts in the bend axes
    cloth.bend_tri_tips = None        # tips on tris opposite the bend axes
    cloth.bend_tris = None            # tris that are evaluated as bend tris
    # Dynamic bend data:
    cloth.bend_weights = None         # barycentric weights for placing tri tips
    cloth.bend_surface_offset = None  # distance along non-unit cross product from tris
    t = T()
    # overwite all the None values
    get_bend_sets(cloth)
    T(t, "time it took to get the bend springs")
    
    # cpoe method for plot
    cloth.axis_div = None
    cloth.cross_div = None
    cloth.tri_div = None
    cpoe_bend_plot_values(cloth)


    # Allocate arrays
    cloth.select_start = np.copy(cloth.co)
    cloth.pin_arr = np.copy(cloth.co)
    cloth.vel = np.zeros_like(cloth.co)
    cloth.vel_zero = np.zeros_like(cloth.co)
    cloth.feedback = np.zeros_like(cloth.co)
    cloth.stretch_array = np.zeros(cloth.co.shape[0], dtype=np.float32) # for calculating the weights of the mean
    
    cloth.target_co = get_co_mode(cloth.target) # (will be None if target is None)
    cloth.velocity = Nx3(ob)
    
    # external connections
    external_co = None
    external_springs = None # 2d edge-like array where right side is idx from the points in an external object
    
    
    # target co
    same = False
    if cloth.target is not None: # if we are doing a two way update we will need to put run the updater here
        same = compare_geometry(ob, cloth.target, cloth.obm, cloth.target_obm)
        if same:
            cloth.source, cloth.dots = stretch_springs_basic(cloth, cloth.target)

    if not same: # there is no matching target or target is None

        cloth.v, cloth.source, cloth.dots = stretch_springs_basic(cloth)

    return cloth

# ^                                                          ^ #
# ^                   END cloth instance                     ^ #
# ============================================================ #



# ============================================================ #
#                     update the cloth                         #
#                                                              #

# update the cloth ---------------
def update_groups(cloth, obm=None, geometry=False):
    """Create of update data in the cloth instance
    related to the vertex groups.
    geometry is run when there are changes in the geomtry"""
    ob = cloth.ob
    current_index = ob.vertex_groups.active_index

    # vertex groups
    current = np.copy(cloth.pin)
    
    # update pin weight
    #pin_idx = ob.vertex_groups['MC_pin'].index
    #ob.vertex_groups.active_index = pin_idx
    cloth.pin = get_weights(ob, 'MC_pin', obm=obm)[:, nax]

    #surface_idx = ob.vertex_groups['MC_surface_follow'].index
    #ob.vertex_groups.active_index = surface_idx
    cloth.surface_vgroup_weights = get_weights(ob, 'MC_surface_follow', obm=obm)[:, nax]

    if geometry:
        old = current.shape[0]
        new = cloth.pin.shape[0]
        dif = new - old
        if dif > 0:
            fix = np.zeros_like(cloth.pin)
            fix[:old] += current
            current = fix
            cloth.pin_arr = np.append(cloth.pin_arr, cloth.co[old:], axis=0)
            zeros = np.zeros_like(cloth.co[old:])
            cloth.velocity = np.append(cloth.velocity, zeros, axis=0)
            cloth.vel_zero = np.copy(cloth.co)
            cloth.feedback = np.copy(cloth.co)
        else:
            cloth.pin_arr = np.copy(cloth.co)        
            cloth.vel_zero = np.copy(cloth.co)
            cloth.feedback = np.copy(cloth.co)
            cloth.velocity = np.zeros_like(cloth.co)
            return
    # !!! Need to store cloth.pin_arr in the save file !!!
    changed = (cloth.pin - current) != 0 # Have to manage the location of the pin verts with weights less than one
    if hasattr(cloth, 'co'):
        cloth.pin_arr[changed.ravel()] = cloth.co[changed.ravel()]

    # update surface weight

    ob.vertex_groups.active_index = current_index


# update the cloth ---------------
def update_selection_from_editmode(cloth):
    select = np.zeros(len(cloth.ob.data.vertices), dtype=np.bool)
    cloth.ob.data.vertices.foreach_get('select', select)
    #cloth.pin_arr[select] = cloth.co[select]


# update the cloth ---------------
def collide(colliders=None):
    print('checked collisions')


# update the cloth ---------------
def obm_co(a, b, i):
    """Runs inside a list comp attempting to improve speed"""
    a[i].co = b[i]


# update the cloth ---------------
def changed_geometry(ob1, ob2):
    """Copy the geometry of ob1 to ob2"""
    # when extruding geometry there is a face
    # or faces the extrued verts come from
    # get barycentric mapping from that face
    # or faces. Remap that to the current
    # state of the cloth object.

    """  OR!!!  """

    # FOR ADDING (so detect if we're adding verts)
    # (If we're just filling in faces it should be more simple)
    # the new verts will always be selected and old ones
    #   will always be deselected.
    # take a shapshot of the current cloth state's
    #   vertex locations
    # overwrite the mesh
    # update the coords from previous verts to the
    # shapshot.


    # FOR REMOVING (should only be for removing verts)
    # no way to know what verts will get deleted
    #



# update the cloth ---------------
def measure_edges(co, idx):
    """Takes a set of coords and an edge idx and measures segments"""
    l = idx[:,0]
    r = idx[:,1]
    v = co[r] - co[l]
    d = np.einsum("ij ,ij->i", v, v)
    return v, d, np.sqrt(d)


def stretch_springs_basic(cloth, target=None): # !!! need to finish this
    """Measure the springs"""
    if target is not None:
        dg = cloth.dg
        #proxy = col.ob.to_mesh(bpy.context.evaluated_depsgraph_get(), True, calc_undeformed=False)
        #proxy = col.ob.to_mesh() # shouldn't need to use mesh proxy because I'm using bmesh
        if cloth.proxy is None:    
            cloth.proxy = target.evaluated_get(dg)
        co = get_co_mode(cloth.proxy) # needs to be depsgraph eval
        # need to get co with modifiers that don't affect the vertex count
        # so I could create a list of mods to turn off then use that fancy
        # thing I created for turning off modifiers in the list.
        return measure_edges(co, cloth.basic_set)

    co = get_co_shape(cloth.ob, 'MC_source')
    # can't figure out how to update new verts to source shape key when
    #   in edit mode. Here we pull from source shape and add verts from
    #   current bmesh where there are new verts. Need to think about
    #   how to fix this so that it blendes correctly with the source
    #   shape or target... Confusing....  Will also need to update
    #   the source shape key with this data once we switch out
    #   of edit mode. If someone is working in edit mode and saves
    #   their file without switching out of edit mode I can't fix
    #   that short of writing these coords to a file.
    if cloth.ob.data.is_editmode:
        co = np.append(co, cloth.co[co.shape[0]:], axis=0)

    return measure_edges(co, cloth.basic_set)


def surface_forces(cloth):

    # surface follow data ------------------------------------------    
    # cloth.surface_vgroup_weights    (weights on the cloth object)
    # cloth.bind_idx = idx            (verts that are bound to the surface)
    tridex = cloth.surface_tridex          # (index of tris in surface object)
    bary = cloth.surface_bary_weights    # (barycentric weights)
    so = cloth.surface_object      # (object we are following)
    
    shape = cloth.surface_tridex.shape
    tri_co = np.array([so.data.vertices[i].co for i in tridex.ravel()], dtype=np.float32)
    tri_co.shape = (shape[0] * 3, 3)
    apply_in_place(cloth.surface_object, tri_co)
    
    tri_co.shape = (shape[0], 3, 3)
    plot = np.sum(tri_co * bary[:, :, nax], axis=1)
        
    # update the normals -----------------
    cloth.surface_norms = get_normals_from_tris(tri_co)
    norms = cloth.surface_norms * cloth.surface_norm_vals
    #print(cloth.surface_norm_vals[0], 'what is this norm val???????')
    plot += norms
    #plot += apply_rotation(cloth.ob, norms)
    
    world_co = apply_in_place(cloth.ob, cloth.co[cloth.bind_idx])
    dif = (plot - world_co) * cloth.surface_vgroup_weights[cloth.bind_idx]
    cloth.co[cloth.bind_idx] += revert_rotation(cloth.ob, dif)


# ==============================================
# ==============================================
# ==============================================
def bend_spring_force_linear(cloth):

    tris = cloth.co[cloth.bend_tris]
    surface_offset = cross_from_tris(tris) * cloth.bend_surface_offset
    plot = np.sum(tris * cloth.bend_weights, axis=1) + surface_offset
    # -----------------------------------------
    bend_stiff = cloth.ob.MC_props.bend
        
    cv = (plot - cloth.co[cloth.bend_tri_tips]) * bend_stiff
    
    # swap the mags so that the larger triangles move a shorter distance
    d = np.einsum('ij,ij->i', cv, cv)
    l = np.sqrt(d)[:, None]
    m1 = np.nan_to_num(l[::2] / l[1::2])
    m2 = np.nan_to_num(l[1::2] / l[::2])
    cv[1::2] *= m1
    cv[::2] *= m2
    
    np.add.at(cloth.co, cloth.bend_tri_tips, cv)    

    # now push the hinge the opposite direction
    sh = cv.shape
    cv.shape = (sh[0]//2,2,3)
    mix = np.mean(cv, axis=1)
    np.subtract.at(cloth.co, cloth.bend_edges, mix[:, None])


def bend_spring_not_bary():
    # get the normal from the opposite tri
    # get the cross of normal and axis.
    # get cpoe on axis
    # get cpoe on normal/axis cross
    # get cpoe on cross for how far up. (x,y,z in three steps)
    # now we have a square that let's us plot the point
    # If we use unit vecs on the cross and axis distortions of the faces
    #   will hopefully be less likely to make things explode.
    
    # !!! Might be able to use this on n-gons. Just pick a point
    #   in the ngon that makes sense for getting a normal with the axis
    pass


def bend_spring_force_mixed(cloth):

    tris = cloth.co[cloth.bend_tris]
    

    cpoe = True
    if cpoe:
        plot = cpoe_bend_plot(cloth)
    else:
        unit = True # for testing unit normalized surface offset
        if unit:
            cross = cross_from_tris(tris)
            U_cross = cross / np.sqrt(np.einsum('ij,ij->i', cross, cross))[:, None]
            surface_offset = U_cross * cloth.bend_U_d[:, None]

        else:
            surface_offset = cross_from_tris(tris) * cloth.bend_surface_offset
        plot = np.sum(tris * cloth.bend_weights, axis=1) + surface_offset
    
        #cloth.green.location = plot[0]
        #cloth.red.location = plot[1]
    # -----------------------------------------
    bend_stiff = cloth.ob.MC_props.bend * 0.2
        
    cv = plot - cloth.co[cloth.bend_tri_tips]
    d = np.einsum('ij,ij->i', cv, cv)
    l = np.sqrt(d)
    
    #if False:
    m1 = np.nan_to_num(l[::2] / l[1::2])
    m2 = np.nan_to_num(l[1::2] / l[::2])
    cv[1::2] *= m1[:, None]
    cv[::2] *= m2[:, None]
    
    # swap l to match
    #l.shape = (l.shape[0] //2, 2)
    #l = l[:,::-1].ravel()
    
    # mean method ----------------------
    cloth.bend_tri_tip_array[:] = 0
    #print(cloth.bend_tri_tip_array.shape, "tri tip array shape")
    #print(cloth.bend_tri_tips.shape, "tri tips shape")
    
    np.add.at(cloth.bend_tri_tip_array, cloth.bend_tri_tips, l)
    weights = np.nan_to_num(l / cloth.bend_tri_tip_array[cloth.bend_tri_tips])
    cv *= weights[:, None]
    cv *= bend_stiff

    np.add.at(cloth.co, cloth.bend_tri_tips, cv)
    sh = cv.shape
    cv.shape = (sh[0]//2,2,3)
    mix = np.mean(cv, axis=1)
    np.subtract.at(cloth.co, cloth.bend_edges, mix[:, None])


def bend_spring_force_U_cross(cloth):

    tris = cloth.co[cloth.bend_tris]
    #surface_offset = cross_from_tris(tris) * cloth.bend_surface_offset
    cross = cross_from_tris(tris)
    U_cross = cross / np.sqrt(np.einsum('ij,ij->i', cross, cross))[:, None]
    surface_offset = U_cross * cloth.bend_U_d[:, None]
    plot = np.sum(tris * cloth.bend_weights, axis=1) + surface_offset
    # -----------------------------------------
    bend_stiff = cloth.ob.MC_props.bend
        
    cv = plot - cloth.co[cloth.bend_tri_tips]
    d = np.einsum('ij,ij->i', cv, cv)
    l = np.sqrt(d) * bend_stiff        
    move_l = l * bend_stiff        
        
    # mean method ----------------------
    cloth.bend_tri_tip_array[:] = 0
    np.add.at(cloth.bend_tri_tip_array, cloth.bend_tri_tips, l)
    weights = np.nan_to_num(move_l / cloth.bend_tri_tip_array[cloth.bend_tri_tips])
    cv *= weights[:, None]
    cv *= bend_stiff

    np.add.at(cloth.co, cloth.bend_tri_tips, cv)
    np.subtract.at(cloth.co, cloth.bend_edges.ravel(), cv)


def spring_basic(cloth):
        
    # get properties
    grav = cloth.ob.MC_props.gravity * 0.001  
    vel = cloth.ob.MC_props.velocity    
    feedback_val = cloth.ob.MC_props.feedback
    stretch = cloth.ob.MC_props.stretch * 0.5
    push = cloth.ob.MC_props.push  
    
    # measure source
    dynamic = True
    if dynamic:
        v, d, l = stretch_springs_basic(cloth, cloth.target) # from target or source key
    
    cloth.select_start[:] = cloth.co

    cloth.co += cloth.velocity
    cloth.vel_zero[:] = cloth.co
    cloth.feedback[:] = cloth.co
    
    s_iters = cloth.ob.MC_props.stretch_iters
    for i in range(s_iters):

        # (current vec, dot, length)
        cv, cd, cl = measure_edges(cloth.co, cloth.basic_set) # from current cloth state
        move_l = (cl - l) * stretch

        # separate push springs
        if push != 1:    
            push_springs = move_l < 0
            move_l[push_springs] *= push
        
        # !!! here we could square move_l to accentuate bigger stretch
        # !!! see if it solves better.
        
        # mean method -------------------
        cloth.stretch_array[:] = 0.0
        rock_hard_abs = np.abs(move_l)
        np.add.at(cloth.stretch_array, cloth.basic_v_fancy, rock_hard_abs)
        weights = np.nan_to_num(rock_hard_abs / cloth.stretch_array[cloth.basic_v_fancy])
        # mean method -------------------
        
        # apply forces ------------------
        #if False:
        move = cv * (np.nan_to_num(move_l / cl)[:,None])
        
        move *= weights[:,None]
        np.add.at(cloth.co, cloth.basic_v_fancy, move)

        if True:
            # test ====================== bend springs
            # test ====================== bend springs
            if cloth.bend_data is not None:    
                bend_spring_force_mixed(cloth)
            # test ====================== bend springs
            # test ====================== bend springs

        # apply surface sew for each iteration:
        if cloth.surface:
            surface_forces(cloth)

        # add pin vecs ------------------
        pin_vecs = (cloth.pin_arr - cloth.co)
        cloth.co += (pin_vecs * cloth.pin)
        #if cloth.ob.MC_props.pause_selected:
        pause_selected = True
        if cloth.ob.data.is_editmode:
            if pause_selected:

                cloth.co[cloth.selected] = cloth.select_start[cloth.selected]
                cloth.pin_arr[cloth.selected] = cloth.select_start[cloth.selected]
    
    # extrapolate maybe? # get spring move, multiply vel by fraction, add spring move
    spring_move = cloth.co - cloth.feedback
    v_move = cloth.co - cloth.vel_zero

    cloth.velocity += v_move
    cloth.velocity += spring_move * feedback_val
    cloth.velocity *= vel    
    
    cloth.velocity[:,2] += grav
    #cloth.velocity[:,2] += (grav * (-cloth.pin + 1).ravel())



# ==============================================
# ==============================================
# ==============================================

# update the cloth ---------------
# Not used. Replaced by spring_basic
def spring_force(cloth):

    # get properties
    grav = cloth.ob.MC_props.gravity * 0.001  
    vel = cloth.ob.MC_props.velocity    
    feedback_val = cloth.ob.MC_props.feedback
    stretch = cloth.ob.MC_props.stretch * 0.5
    push = cloth.ob.MC_props.push  
    
    # measure source
    dynamic = True
    if dynamic:
        v, d, l = stretch_springs(cloth, cloth.target) # from target or source key
    
    cloth.select_start[:] = cloth.co

    cloth.co += cloth.velocity
    cloth.vel_zero[:] = cloth.co
    cloth.feedback[:] = cloth.co
    
    iters = cloth.ob.MC_props.iters
    for i in range(iters):

        # apply pin force each iteration
        #pin_vecs = (cloth.pin_arr - cloth.co) * cloth.pin
        #cloth.co += pin_vecs

        # (current vec, dot, length)
        cv, cd, cl = measure_edges(cloth.co, cloth.springs) # from current cloth state
        move_l = (cl - l) * stretch

        # separate push springs
        if push != 1:    
            push_springs = move_l < 0
            move_l[push_springs] *= push
        
        # !!! here we could square move_l to accentuate bigger stretch
        # !!! see if it solves better.
        
        # mean method -------------------
        cloth.stretch_array[:] = 0.0
        rock_hard_abs = np.abs(move_l)[cloth.e_fancy]
        np.add.at(cloth.stretch_array, cloth.v_fancy, rock_hard_abs)
        weights = np.nan_to_num(rock_hard_abs / cloth.stretch_array[cloth.v_fancy])
        # mean method -------------------
        
        # apply forces ------------------
        move = cv * np.nan_to_num(move_l / cl)[:,None]
        midx = move[cloth.e_fancy]
        midx *= (cloth.flip * (weights)[:,None])
        np.add.at(cloth.co, cloth.v_fancy, midx)

        # apply surface sew for each iteration:
        if cloth.surface:
            surface_forces(cloth)

        # add pin vecs ------------------
        pin_vecs = (cloth.pin_arr - cloth.co)
        cloth.co += (pin_vecs * cloth.pin)
        #if cloth.ob.MC_props.pause_selected:
        pause_selected = True
        if cloth.ob.data.is_editmode:
            if pause_selected:
                cloth.co[cloth.selected] = cloth.select_start[cloth.selected]
                cloth.pin_arr[cloth.selected] = cloth.select_start[cloth.selected]
    
    # extrapolate maybe? # get spring move, multiply vel by fraction, add spring move
    spring_move = cloth.co - cloth.feedback
    v_move = cloth.co - cloth.vel_zero

    cloth.velocity += v_move
    cloth.velocity += spring_move * feedback_val
    cloth.velocity *= vel    
    
    cloth.velocity[:,2] += grav
    #cloth.velocity[:,2] += (grav * (-cloth.pin + 1).ravel())



# update the cloth ---------------
def cloth_physics(ob, cloth, collider):
    # can run in edit mode if I deal with looping through bmesh verts
    # will also have to check for changes in edge count, vert count, and face count.
    # if any of the geometry counts change I will need to update springs and other data.
    # If there is a proxy object will need to check that they match and issue
    #   warnings if there is a mismatch. Might want the option to regen the proxy object
    #   or adapt the cloth object to match so I can sync a patter change
    #   given you can change both now I have to also include logic to
    #   decide who is boss if both are changed in different ways.
    #grav = np.array([0,0,-0.1])
    if cloth.target is not None:

        # if target is deleted while still referenced by pointer property
        if len(cloth.target.users_scene) == 0:
            ob.MC_props.target = None
            cloth.target = None # (gets overwritten by cb_target)
            cloth.target_undo = False
            cloth.target_geometry = None # (gets overwritten by cb_target)
            cloth.target_mode = 1
            return

        if cloth.target.data.is_editmode:
            if cloth.target_mode == 1 or cloth.target_undo:
                cloth.target_obm = get_bmesh(cloth.target)
                cloth.target_obm.verts.ensure_lookup_table()
                cloth.target_undo = False
            cloth.target_mode = None

        # target in object mode:
        else: # using else so it won't also run in edit mode
            pass

    dynamic_source = True # can map this to a prop or turn it on and off automatically if use is in a mode that makes it relevant.
    # If there is a target dynamic should prolly be on or if switching from active shape MC_source when in edit mode
    if dynamic_source:
        if cloth.target is not None:
            if not cloth.data.is_editmode: # can use bmesh prolly if not OBJECT mode.
                dg = cloth.dg
                if cloth.proxy is None:
                    cloth.proxy = cloth.target.evaluated_get(dg)
                #proxy = col.ob.to_mesh(bpy.context.evaluated_depsgraph_get(), True, calc_undeformed=False)
                #proxy = col.ob.to_mesh() # shouldn't need to use mesh proxy because I'm using bmesh

                co_overwrite(cloth.proxy, cloth.target_co)


    if ob.data.is_editmode:
        # prop to go into user preferences. (make it so it won't run in edit mode)
        pause_in_edit = False
        if pause_in_edit:
            return

        # if we switch to a different shape key in edit mode:
        index = ob.data.shape_keys.key_blocks.find('MC_current')
        if ob.active_shape_key_index != index:
            cloth.update_lookup = True
            cloth.ob.update_from_editmode()
            bary_bend_springs(cloth)
            cpoe_bend_plot_values(cloth)
            return
        
        # bmesh gets removed when someone clicks on MC_current shape"
        try:
            cloth.obm.verts
        except:
            cloth.obm = get_bmesh(ob)

        if cloth.update_lookup:
            cloth.obm.verts.ensure_lookup_table()
            cloth.update_lookup = False

        # If we switched to edit mode or started in edit mode:
        if cloth.mode == 1 or cloth.undo:
            cloth.obm = get_bmesh(ob)
            cloth.obm.verts.ensure_lookup_table()
            cloth.undo = False
        cloth.mode = None
        # -----------------------------------

        # detect changes in geometry and update
        if cloth.obm is None:
            cloth.obm = get_bmesh(ob)
        same, faces = detect_changes(cloth.geometry, cloth.obm)
        if faces: # zero faces in mesh do nothing
            return
        if not same:
            # for pinning
            print("DANGER!!!!!!!!!!!!!!!!!!")
            print("DANGER!!!!!!!!!!!!!!!!!!")
            print("DANGER!!!!!!!!!!!!!!!!!!")
            print("DANGER!!!!!!!!!!!!!!!!!!")
            print("DANGER!!!!!!!!!!!!!!!!!!")
            print("DANGER!!!!!!!!!!!!!!!!!!")
            np.copyto(cloth.pin_arr, cloth.co)
            #cloth.springs, cloth.v_fancy, cloth.e_fancy, cloth.flip = get_springs(cloth, cloth.obm)
            get_springs_2(cloth)
            get_bend_sets(cloth)
            cpoe_bend_plot_values(cloth)
            cloth.geometry = get_mesh_counts(ob, cloth.obm)
            # cloth.sew_springs = get_sew_springs() # build
            cloth.obm.verts.ensure_lookup_table()
            cloth.select_start = get_co_edit(None, cloth.obm)
            cloth.co = np.array([v.co for v in cloth.obm.verts])
            cloth.stretch_array = np.zeros(cloth.co.shape[0], dtype=np.float32)
            cloth.selected = np.array([v.select for v in cloth.obm.verts])

            update_groups(cloth, cloth.obm, True)
            cloth.ob.update_from_editmode()
            cloth.obm.verts.ensure_lookup_table()
        # updating the mesh coords -----------------@@
        # detects user changes to the mesh like grabbing verts
        #t = T()
        cloth.co = np.array([v.co for v in cloth.obm.verts])
        #T(t, "list comp")

        
        #t = T()
        # doesn't update grab changes.
        #cloth.obm.to_mesh(cloth.ob.data)
        #get_co_mode_2(cloth.ob, cloth.co)
        #print(cloth.co)
        #bmesh.update_edit_mesh(ob.data)
        #T(t, "co_mode_2")
        
        pause_selected = True
        if pause_selected: # create this property for the user (consider global settings for all meshes)
            #cloth.ob.update_from_editmode()
            #ob.data.vertices.foreach_get('select', cloth.selected)
            #cloth.ob.data.vertices.foreach_get('co', cloth.co.ravel())
            cloth.selected = np.array([v.select for v in cloth.obm.verts])
        """======================================"""
        """======================================"""
        # FORCES FORCES FORCES FORCES FORCES

        
        spring_basic(cloth)
        # FORCES FORCES FORCES FORCES FORCES
        """======================================"""
        """======================================"""

        # write vertex coordinates back to bmesh

        for i in range(cloth.co.shape[0]):
            cloth.obm.verts[i].co = cloth.co[i]
        
        #cloth.ob.data.vertices.foreach_set('co', cloth.co.ravel())
        #ob.data.update()
                    
        bmesh.update_edit_mesh(ob.data)
        if False: # (there might be a much faster way by writing to a copy mesh then loading copy to obm)
            bmesh.ops.object_load_bmesh(bm, scene, object)
        # -----------------------------------------@@
        return

    if cloth.mode is None:
        # switched out of edit mode
        #cloth.ob.update_from_editmode()
        cloth.mode = 1
        cloth.obm = bmesh.new()
        cloth.obm.from_mesh(cloth.ob.data)
        update_groups(cloth, cloth.obm)
        update_selection_from_editmode(cloth)
        #cloth.vel_start = cloth.co

    # OBJECT MODE ====== :
    #cloth.co = get_co_shape(cloth.ob, "MC_current")


    """ =============== FORCES OBJECT MODE ================ """
    # FORCES FORCES FORCES FORCES

    #cloth.co += grav
    if False:    
        spring_force(cloth)
    spring_basic(cloth)
    # FORCES FORCES FORCES FORCES
    """ =============== FORCES OBJECT MODE ================ """

    # updating the mesh coords -----------------@@
    shape = cloth.co.shape
    cloth.co.shape = (shape[0] * 3,)
    ob.data.shape_keys.key_blocks['MC_current'].data.foreach_set("co", cloth.co)
    cloth.co.shape = shape
    cloth.ob.data.update()



# update the cloth ---------------
def update_cloth(type=0):

    # run from either the frame handler or the timer
    if type == 0:
        cloths = [i[1] for i in MC_data['cloths'].items() if i[1].ob.MC_props.continuous]
        if len(cloths) == 0:
            bpy.app.timers.unregister(cloth_main)

    if type == 1:
        cloths = [i[1] for i in MC_data['cloths'].items() if i[1].ob.MC_props.animated]
        if len(cloths) == 0:
            install_handler(continuous=True, clear=False, clear_anim=True)

    # check collision objects
    colliders = [i[1] for i in MC_data['colliders'].items() if i[1].ob.MC_props.collider]

    for cloth in cloths:
        cloth_physics(cloth.ob, cloth, colliders)

    #print([i.ob.name for i in cloths], "list of cloths")
    #print([i.ob.name for i in colliders], "list of colliders")
    return


# ^                                                          ^ #
# ^                 END update the cloth                     ^ #
# ============================================================ #


# ============================================================ #
#                      Manage handlers                         #
#                                                              #
# handler ------------------
@persistent
def undo_frustration(scene):
    # someone might edit a mesh then undo it.
    # in this case I need to recalc the springs and such.
    # using id props because object memory adress changes with undo

    # find all the cloth objects in the scene and put them into a list
    cloths = [i for i in bpy.data.objects if i.MC_props.cloth]
    # throw an id prop on there.
    for i in cloths:
        cloth = MC_data['cloths'][i['MC_cloth_id']]
        cloth.ob = i
        # update for meshes in edit mode
        cloth.undo = True
        cloth.target_undo = True
        try:
            cloth.obm.verts
        except:
            cloth.obm = get_bmesh(cloth.ob)
        
        
        if not detect_changes(cloth.geometry, cloth.obm)[0]:
            cloth.springs, cloth.v_fancy, cloth.e_fancy, cloth.flip = get_springs(cloth)

    # find all the collider objects in the scene and put them into a list
    colliders = [i for i in bpy.data.objects if i.MC_props.collider]
    for i in colliders:
        col = MC_data['colliders'][i['MC_collider_id']]
        col.ob = i
        # update for meshes in edit mode
        col.undo = True

    fun = ["your shoe laces", "something you will wonder about but never notice", "something bad because it loves you", "two of the three things you accomplished at work today", "knots in the threads that hold the fabric of the universe", "a poor financial decision you made", "changes to your online dating profile", "your math homework", "everything you've ever accomplished in life", "something you'll discover one year from today", "the surgery on your cat", "your taxes", "all the mistakes you made as a child", "the mess you made in the bathroom", "the updates to your playstation 3", "nothing! Modeling Cloth makes no mistakes!", "your last three thoughts and you'll never know what the"]
    print("Modeling Cloth undid " + fun[MC_data["iterator"]])
    MC_data['iterator'] += 1
    if MC_data['iterator'] == len(fun):
        MC_data['iterator'] = 0


# handler ------------------
@persistent
def cloth_main(scene=None):
    """Runs the realtime updates"""

    total_time = T()

    kill_me = []
    # check for deleted cloth objects
    for id, val in MC_data['cloths'].items():
        try:
            val.ob.data
        except:
            # remove from dict
            kill_me.append(id)

    for i in kill_me:
        del(MC_data['cloths'][i])
        print('killed wandering cloths')

    kill_me = []
    # check for deleted collider objects
    for id, val in MC_data['colliders'].items():
        try:
            val.ob.data
        except:
            # remove from dict
            kill_me.append(id)

    for i in kill_me:
        del(MC_data['colliders'][i])
        print('killed wandering colliders')

    # run the update -------------
    type = 1 # frame handler or timer continuous
    if scene is None:
        type=0
    update_cloth(type) # type 0 continuous, type 1 animated
    # ----------------------------

    MC_data['count'] += 1
    print('frame: ', MC_data['count'])

    # auto-kill
    auto_kill = True
    auto_kill = False
    if auto_kill:
        if MC_data['count'] == 20:
            print()
            print('--------------')
            print('died')
            return

    delay = bpy.context.scene.MC_props.delay# !! put this into a user property !!
    T(total_time, "Total time in handler")
    return delay


# handler ------------------
def install_handler(continuous=True, clear=False, clear_anim=False):
    """Run this when hitting continuous update or animated"""
    # clean dead versions of the animated handler
    handler_names = np.array([i.__name__ for i in bpy.app.handlers.frame_change_post])
    booly = [i == 'cloth_main' for i in handler_names]
    idx = np.arange(handler_names.shape[0])
    idx_to_kill = idx[booly]
    for i in idx_to_kill[::-1]:
        del(bpy.app.handlers.frame_change_post[i])
        print("deleted handler ", i)
    if clear_anim:
        print('ran clear anim handler')
        return

    # clean dead versions of the timer
    if bpy.app.timers.is_registered(cloth_main):
        bpy.app.timers.unregister(cloth_main)

    # for removing all handlers and timers
    if clear:
        print('ran clear handler')
        return

    MC_data['count'] = 0

    if np.any([i.MC_props.continuous for i in bpy.data.objects]):
        # continuous handler
        bpy.app.timers.register(cloth_main, persistent=True)
        #bpy.app.timers.register(funky.partial(cloth_main, delay, kill, T), first_interval=delay_start, persistent=True)
        return

    # animated handler
    if np.any([i.MC_props.animated for i in bpy.data.objects]):
        bpy.app.handlers.frame_change_post.append(cloth_main)


# ^                                                          ^ #
# ^                      END handler                         ^ #
# ============================================================ #


# ============================================================ #
#                    callback functions                        #
#                                                              #


# calback functions ---------------
def oops(self, context):
    # placeholder for reporting errors or other messages
    return

# calback functions ---------------
# object:

def cb_collider(self, context):
    """Set up object as collider"""

    ob = bpy.context.object
    if ob.type != "MESH":
        self['collider'] = False

        # Report Error
        msg = "Must be a mesh. Collisions with non-mesh objects can create black holes potentially destroying the universe."
        bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
        return

    # The object is the key to the cloth instance in MC_data
    if self.collider:
        collider = create_collider()

        d_keys = [i for i in MC_data['colliders'].keys()]
        id_number = 0

        if len(d_keys) > 0:
            id_number = max(d_keys) + 1
            print("created new collider id", id_number)

        MC_data['colliders'][id_number] = collider
        print('created collider instance')

        ob['MC_collider_id'] = id_number
        print(MC_data['colliders'])
        return

    # when setting collider to False
    if ob['MC_collider_id'] in MC_data['colliders']:
        del(MC_data['colliders'][ob['MC_collider_id']])
        del(ob['MC_collider_id'])

# calback functions ---------------
# object:
def cb_cloth(self, context):
    """Set up object as cloth"""

    ob = bpy.context.object

    # set the recent object for keeping settings active when selecting empties
    recent = MC_data['recent_object']
        
    if ob.type != "MESH":
        if recent is not None:
            ob = recent    
        else:    
            self['cloth'] = False

            # Report Error
            msg = "Must be a mesh. Non-mesh objects make terrible shirts."
            bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
            return

    if len(ob.data.polygons) < 1:
        self['cloth'] = False

        # Report Error
        msg = "Must have at least one face. Faceless meshes are creepy."
        bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
        return


    # The custom object id is the key to the cloth instance in MC_data
    if self.cloth:
        # creat shape keys and set current to active
        reset_shapes(ob)
        index = ob.data.shape_keys.key_blocks.find('MC_current')
        ob.active_shape_key_index = index

        cloth = create_instance()

        # recent_object allows cloth object in ui
        #   when selecting empties such as for pinning.
        MC_data['recent_object'] = bpy.context.object

        # use an id prop so we can find the object after undo
        d_keys = [i for i in MC_data['cloths'].keys()]
        id_number = 0
        if len(d_keys) > 0:
            id_number = max(d_keys) + 1
            print("created new cloth id", id_number)

        MC_data['cloths'][id_number] = cloth
        ob['MC_cloth_id'] = id_number
        print('created instance')
        return

    # when setting cloth to False
    if ob['MC_cloth_id'] in MC_data['cloths']:
        del(MC_data['cloths'][ob['MC_cloth_id']])
        del(ob['MC_cloth_id'])
        # recent_object allows cloth object in ui
        #   when selecting empties such as for pinning
        MC_data['recent_object'] = None
        ob.MC_props['continuous'] = False
        ob.MC_props['animated'] = False


# calback functions ----------------
# object:
def cb_continuous(self, context):
    """Turn continuous update on or off"""
    install_handler(continuous=True)
    ob = bpy.context.object

    # updates groups when we toggle "Continuous"
    recent = MC_data['recent_object']
    if recent is not None:
        if ob.type != 'MESH':
            ob = recent
        
        
    cloth = MC_data["cloths"][ob['MC_cloth_id']]
    
    """need to test this and fix if needed. Test adding geometry while paused.
    Need to work with pinning. If a person works with the cloth
    and decides to pin something in it's current state
    it will reset the pinned verts to the basis. Don't want that!!!"""
    
    if ob.data.is_editmode:
        return
        cloth.co = np.array([v.co for v in cloth.obm.verts])
        update_groups(cloth, cloth.obm)

        #translate_vecs = cloth.pin_arr - cloth.co
        #np.copyto(cloth.co, cloth.pin_arr)
        #np.copyto(cloth.pin_arr, cloth.co)
        #cloth.pin_arr += translate_vecs


        return
    cloth.co = get_co_shape(ob, key='MC_current')
    update_groups(cloth, None)
    return


# calback functions ----------------
# object:
def cb_animated(self, context):
    """Turn animated update on or off"""
    install_handler(continuous=False)

    # updates groups when we toggle "Animated"
    ob = bpy.context.object
    cloth = MC_data["cloths"][ob['MC_cloth_id']]
    if ob.data.is_editmode:
        cloth.co = np.array([v.co for v in cloth.obm.verts])
        update_groups(cloth, cloth.obm)
        return
    cloth.co = get_co_shape(ob, key='MC_current')
    update_groups(cloth, None)


# calback functions ----------------
# object:
def cb_target(self, context):
    """Use this object as the source target"""

    # if the target object is deleted while an object is using it:
    if bpy.context.object is None:
        return

    # setting the property normally
    ob = bpy.context.object

    cloth = MC_data["cloths"][ob['MC_cloth_id']]

    # kill target data
    if self.target is None:
        cloth.target = None
        return

    # kill target data
    cloth.proxy = bpy.context.evaluated_get(self.target)
    same = compare_geometry(ob, proxy, obm1=None, obm2=None, all=False)
    if not same:
        msg = "Vertex and Face counts must match. Sew edges don't have to match."
        bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
        self.target = None
        cloth.target = None
        return

    # Ahh don't kill me I'm a valid target!
    print(self.target, "this should be target dot namey poo")
    cloth.target = self.target
    cloth.target_geometry = get_mesh_counts(cloth.target)
    cloth.target_co = get_co_mode(cloth.target)


# calback functions ----------------
# object:
def cb_reset(self, context):
    """RESET button"""
    ob = MC_data['recent_object']
    if ob is None:
        ob = bpy.context.object
    cloth = MC_data["cloths"][ob['MC_cloth_id']]
    #RESET(cloth)
    self['reset'] = False


# calback functions ----------------
# scene:
def cb_pause_all(self, context):
    print('paused all')


# calback functions ----------------
# scene:
def cb_play_all(self, context):
    print('play all')


# calback functions ----------------
# scene:
def cb_duplicator(self, context):
    # DEBUG !!!
    # kills or restarts the duplicator/loader for debugging purposes
    if not bpy.app.timers.is_registered(duplication_and_load):
        bpy.app.timers.register(duplication_and_load)
        return

    bpy.app.timers.unregister(duplication_and_load)
    print("unloaded dup/load timer")

# ^                                                          ^ #
# ^                 END callback functions                   ^ #
# ============================================================ #


# ============================================================ #
#                     create properties                        #
#                                                              #

# create properties ----------------
# object:
class McPropsObject(bpy.types.PropertyGroup):

    collider:\
    bpy.props.BoolProperty(name="Collider", description="Cloth objects collide with this object", default=False, update=cb_collider)

    cloth:\
    bpy.props.BoolProperty(name="Cloth", description="Set this as a cloth object", default=False, update=cb_cloth)

    # handler props for each object
    continuous:\
    bpy.props.BoolProperty(name="Continuous", description="Update cloth continuously", default=False, update=cb_continuous)

    animated:\
    bpy.props.BoolProperty(name="Animated", description="Update cloth only when animation is running", default=False, update=cb_animated)

    target:\
    bpy.props.PointerProperty(type=bpy.types.Object, description="Use this object as the target for stretch and bend springs", update=cb_target)

    # Forces
    gravity:\
    bpy.props.FloatProperty(name="Gravity", description="Strength of the gravity", default=0.0, min=-1000, max=1000, soft_min= -10, soft_max=10, precision=3)

    velocity:\
    bpy.props.FloatProperty(name="Velocity", description="Maintains Velocity", default=0.777, min= -1000, max=1000, soft_min= 0.0, soft_max=1, precision=3)

    wind:\
    bpy.props.FloatProperty(name="Wind", description="This Really Blows", default=0.0, min= -1000, max=1000, soft_min= -10.0, soft_max=10.0, precision=3)

    # stiffness
    feedback:\
    bpy.props.FloatProperty(name="Feedback", description="Extrapolate for faster solve", default=1, min= -1000, max=1000, soft_min= 0.0, soft_max=1, precision=3)

    stretch_iters:\
    bpy.props.IntProperty(name="Iters", description="Number of iterations of cloth solver", default=2, min=0, max=1000)#, precision=1)

    stretch:\
    bpy.props.FloatProperty(name="Stretch", description="Strength of the stretch springs", default=1, min=0, max=10, soft_min= 0, soft_max=1, precision=3)

    push:\
    bpy.props.FloatProperty(name="Push", description="Strength of the push springs", default=1, min=0, max=1, soft_min= -2, soft_max=2, precision=3)

    bend_iters:\
    bpy.props.IntProperty(name="Bend Iters", description="Number of iterations of bend springs", default=2, min=0, max=1000)#, precision=1)

    bend:\
    bpy.props.FloatProperty(name="Bend", description="Strength of the bend springs", default=1, min=0, max=10, soft_min= 0, soft_max=1, precision=3)

    # Sewing
    sew_force:\
    bpy.props.FloatProperty(name="Sew Force", description="Shrink Sew Edges", default=0.1, min=0, max=1, soft_min= -100, soft_max=100, precision=3)
    
    surface_follow_selection_only:\
    bpy.props.BoolProperty(name="Use Selected Faces", description="Bind only to selected faces", default=False)
    
    # Vertex Groups
    vg_pin:\
    bpy.props.FloatProperty(name="Pin", description="Pin Vertex Group", default=0, min=0, max=1, soft_min= -2, soft_max=2, precision=3)

    vg_drag:\
    bpy.props.FloatProperty(name="Drag", description="Drag Vertex Group", default=0, min=0, max=1, soft_min= -2, soft_max=2, precision=3)

    vg_surface_follow:\
    bpy.props.FloatProperty(name="Surface Follow", description="Surface Follow Vertex Group", default=0, min=0, max=1, soft_min= -2, soft_max=2, precision=3)
        
    

# create properties ----------------
# scene:
class McPropsScene(bpy.types.PropertyGroup):

    kill_duplicator:\
    bpy.props.BoolProperty(name="kill duplicator/loader", description="", default=False, update=cb_duplicator)

    pause_all:\
    bpy.props.BoolProperty(name="Pause All", description="", default=False, update=cb_pause_all)

    play_all:\
    bpy.props.BoolProperty(name="Play all", description="", default=False, update=cb_play_all)

    delay:\
    bpy.props.FloatProperty(name="Delay", description="Slow down the continuous update", default=0, min=0, max=100)

# ^                                                          ^ #
# ^                     END properties                       ^ #
# ============================================================ #


# ============================================================ #
#                    registered operators                      #
#                                                              #

class MCResetToBasisShape(bpy.types.Operator):
    """Reset the cloth to basis shape"""
    bl_idname = "object.mc_reset_to_basis_shape"
    bl_label = "MC Reset To Basis Shape"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object
        cloth = get_cloth(ob)
        if ob.data.is_editmode:
            Basis = cloth.obm.verts.layers.shape["Basis"]
            for v in cloth.obm.verts:
                v.co = v[Basis]

        reset_shapes(ob)
        cloth.co = get_co_shape(ob, "Basis")
        cloth.velocity[:] = 0
        cloth.pin_arr[:] = cloth.co
        cloth.feedback[:] = 0
        cloth.select_start[:] = cloth.co
        
        current_key = ob.data.shape_keys.key_blocks['MC_current'] 
        current_key.data.foreach_set('co', cloth.co.ravel())
        ob.data.update()
        return {'FINISHED'}


class MCResetSelectedToBasisShape(bpy.types.Operator):
    """Reset the selected verts to basis shape"""
    bl_idname = "object.mc_reset_selected_to_basis_shape"
    bl_label = "MC Reset Selected To Basis Shape"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object
        cloth = get_cloth(ob)
        if ob.data.is_editmode:
            Basis = cloth.obm.verts.layers.shape["Basis"]
            for v in cloth.obm.verts:
                if v.select:
                    v.co = v[Basis]

        reset_shapes(ob)
        bco = get_co_shape(ob, "Basis")
        cloth.co[cloth.selected] = bco[cloth.selected]
        cloth.pin_arr[cloth.selected] = bco[cloth.selected]
        cloth.select_start[cloth.selected] = bco[cloth.selected]
        cloth.feedback[cloth.selected] = 0
        
        bco[~cloth.selected] = cloth.co[~cloth.selected]
        ob.data.shape_keys.key_blocks['MC_current'].data.foreach_set('co', bco.ravel())
        ob.data.update()

        return {'FINISHED'}


class MCSurfaceFollow(bpy.types.Operator):
    """Connect points to nearest surface"""
    bl_idname = "object.mc_surface_follow"
    bl_label = "MC Surface Follow"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        
        active = bpy.context.object        
        if active is None:
            msg = "Must have an active mesh"
            bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
            return {'FINISHED'}
        
        if active.type != 'MESH':
            msg = "Active object must be a mesh"
            bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
            return {'FINISHED'}
            
        if not active.data.polygons:
            msg = "Must have at least one face in active mesh"
            bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
            return {'FINISHED'}
        
        cloths = [i for i in bpy.data.objects if ((i.MC_props.cloth) & (i is not active) & (i.select_get()))]        
        if not cloths:
            msg = "Must select at least one cloth object and an active object to bind to"
            bpy.context.window_manager.popup_menu(oops, title=msg, icon='ERROR')
            return {'FINISHED'}
        
        # writes to cloth instance
        create_surface_follow_data(active, cloths)

        return {'FINISHED'}


class MCCreateSewLines(bpy.types.Operator):
    """Create sew lines between sets of points"""
    bl_idname = "object.mc_create_sew_lines"
    bl_label = "MC Create Sew Lines"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object

        #mode = ob.mode
        #if ob.data.is_editmode:
            #bpy.ops.object.mode_set(mode='OBJECT')

        cloth = MC_data['cloths'][ob['MC_cloth_id']]
        
        #bco = get_co_shape(ob, "Basis")

        #bpy.ops.object.mode_set(mode=mode)
        #ob.data.update()
        return {'FINISHED'}


class MCSewToSurface(bpy.types.Operator):
    """Draw a line on the surface and sew to it"""
    bl_idname = "object.mc_sew_to_surface"
    bl_label = "MC Create Surface Sew Line"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object

        #mode = ob.mode
        #if ob.data.is_editmode:
            #bpy.ops.object.mode_set(mode='OBJECT')

        cloth = MC_data['cloths'][ob['MC_cloth_id']]
        
        #bco = get_co_shape(ob, "Basis")

        #bpy.ops.object.mode_set(mode=mode)
        #ob.data.update()
        return {'FINISHED'}


class MCCreateVirtualSprings(bpy.types.Operator):
    """Create Virtual Springs Between Selected Verts"""
    bl_idname = "object.mc_create_virtual_springs"
    bl_label = "MC Create Virtual Springs"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object

        cloth = get_cloth(ob)
        obm = cloth.obm
        verts = np.array([v.index for v in obm.verts if v.select])
        cloth.virtual_spring_verts = verts
        virtual_springs(cloth)
        
        return {'FINISHED'}


class MCApplyForExport(bpy.types.Operator):
    # !!! Not Finished !!!!!!
    """Apply cloth effects to mesh for export."""
    bl_idname = "object.MC_apply_for_export"
    bl_label = "MC Apply For Export"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = get_last_object()[1]
        v_count = len(ob.data.vertices)
        co = np.zeros(v_count * 3, dtype=np.float32)
        ob.data.shape_keys.key_blocks['modeling cloth key'].data.foreach_get('co', co)
        ob.data.shape_keys.key_blocks['Basis'].data.foreach_set('co', co)
        ob.data.shape_keys.key_blocks['Basis'].mute = True
        ob.data.shape_keys.key_blocks['Basis'].mute = False
        ob.data.vertices.foreach_set('co', co)
        ob.data.update()

        return {'FINISHED'}
    
    
class MCVertexGroupPin(bpy.types.Operator):
    """Add Selected To Pin Vertex Group"""
    bl_idname = "object.mc_vertex_group_pin"
    bl_label = "MC Vertex Group Pin"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ob = MC_data['recent_object']
        if ob is None:
            ob = bpy.context.object

        cloth = MC_data['cloths'][ob['MC_cloth_id']]
        
        return {'FINISHED'}
    

# ^                                                          ^ #
#                  END registered operators                    #
# ============================================================ #


# ============================================================ #
#                         draw code                            #
#                                                              #
class PANEL_PT_MC_Master(bpy.types.Panel):
    """MC Panel"""
    bl_label = "MC Master Panel"
    bl_idname = "PANEL_PT_mc_master_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Extended Tools"

    @classmethod
    def poll(cls, context):
        ob = bpy.context.object
        if ob is None:
            return False
        
        if ob.type != 'MESH':
            if MC_data['recent_object'] is None:
                return False
            ob = MC_data['recent_object']
        return True
           
    def __init__(self):
        ob = bpy.context.object
        if ob.type != 'MESH':
            ob = MC_data['recent_object']
        
        self.ob = ob
        self.cloth = ob.MC_props.cloth

        
# MAIN PANEL
class PANEL_PT_modelingClothMain(PANEL_PT_MC_Master, bpy.types.Panel):
    """Modeling Cloth Main"""
    bl_label = "MC Main"
    bl_idname = "PANEL_PT_modeling_cloth_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Extended Tools"

    def draw(self, context):
        sc = bpy.context.scene
        layout = self.layout
        col = layout.column(align=True)
        col.prop(sc.MC_props, "kill_duplicator", text="kill_duplicator", icon='DUPLICATE')
        # use current mesh or most recent cloth object if current ob isn't mesh
        ob = self.ob

        # if we select a new mesh object we want it to display

        col = layout.column(align=True)
        # display the name of the object if "cloth" is True
        #   so we know what object is the recent object
        recent_name = ''
        if ob.MC_props.cloth:
            recent_name = ob.name
        col.prop(ob.MC_props, "cloth", text="Cloth " + recent_name, icon='MOD_CLOTH')
        col.prop(ob.MC_props, "collider", text="Collide", icon='MOD_PHYSICS')
        if ob.MC_props.cloth:
            #if self.mesh:
            col.label(text='Update Mode')
            col = layout.column(align=True)
            #col.scale_y = 1
            row = col.row()
            row.scale_y = 2
            row.prop(ob.MC_props, "animated", text="Animated", icon='PLAY')
            row = col.row()
            row.scale_y = 2
            row.prop(ob.MC_props, "continuous", text="Continuous", icon='FILE_REFRESH')
            row = col.row()
            row.scale_y = 1
            row.prop(sc.MC_props, "delay", text="Delay", icon='SORTTIME')
            box = col.box()
            #row = col.row()
            box.scale_y = 2
            box.operator('object.mc_reset_to_basis_shape', text="RESET", icon='RECOVER_LAST')
            box.operator('object.mc_reset_selected_to_basis_shape', text="RESET SELECTED", icon='RECOVER_LAST')
            col = layout.column(align=True)
            col.use_property_decorate = True
            col.label(text='Target Object')
            col.prop(ob.MC_props, "target", text="", icon='DUPLICATE')


# SEWING PANEL
class PANEL_PT_modelingClothSewing(PANEL_PT_MC_Master, bpy.types.Panel):
    """Modeling Cloth Settings"""
    bl_label = "MC Sewing"
    bl_idname = "PANEL_PT_modeling_cloth_sewing"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Extended Tools"

    def draw(self, context):
        ob = self.ob
        cloth = ob.MC_props.cloth
        if cloth:
            sc = bpy.context.scene
            layout = self.layout

            # use current mesh or most recent cloth object if current ob isn't mesh
            MC_data['recent_object'] = ob
            col = layout.column(align=True)
            col.scale_y = 1
            col.label(text='Sewing')
            col.prop(ob.MC_props, "sew_force", text="sew_force")

            box = col.box()
            box.scale_y = 2
            box.operator('object.mc_create_virtual_springs', text="Virtual Springs", icon='AUTOMERGE_ON')
            box.operator('object.mc_create_sew_lines', text="Sew Lines", icon='AUTOMERGE_OFF')
            box.operator('object.mc_sew_to_surface', text="Surface Sewing", icon='MOD_SMOOTH')

            return
        sc = bpy.context.scene
        layout = self.layout
        col = layout.column(align=True)
        box = col.box()
        box.scale_y = 2
        box.operator('object.mc_surface_follow', text="Follow Surface", icon='OUTLINER_DATA_SURFACE')        
        box = col.box()
        box.scale_y = 1
        box.prop(ob.MC_props, "surface_follow_selection_only", text="Selected Polys Only")    


# SETTINGS PANEL
class PANEL_PT_modelingClothSettings(PANEL_PT_MC_Master, bpy.types.Panel):
    """Modeling Cloth Settings"""
    bl_label = "MC Settings"
    bl_idname = "PANEL_PT_modeling_cloth_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Extended Tools"

    def draw(self, context):
        ob = self.ob
        cloth = ob.MC_props.cloth
        if cloth:
            sc = bpy.context.scene
            layout = self.layout

            # use current mesh or most recent cloth object if current ob isn't mesh
            MC_data['recent_object'] = ob
            col = layout.column(align=True)
            col.scale_y = 1.5
            col.label(text='Forces')
            col.prop(ob.MC_props, "gravity", text="gravity")
            col.prop(ob.MC_props, "velocity", text="velocity")

            #col.scale_y = 1
            col = layout.column(align=True)
            col.prop(ob.MC_props, "stretch_iters", text="stretch iters")
            col.prop(ob.MC_props, "stretch", text="stretch")
            col.prop(ob.MC_props, "push", text="push")
            col.prop(ob.MC_props, "feedback", text="feedback")
            col.prop(ob.MC_props, "bend_iters", text="bend iters")
            col.prop(ob.MC_props, "bend", text="bend")
            

class PANEL_PT_modelingClothVertexGroups(PANEL_PT_MC_Master, bpy.types.Panel):
    """Modeling Cloth Vertex Groups"""
    bl_label = "MC Vertex Groups"
    bl_idname = "PANEL_PT_modeling_cloth_vertex_groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Extended Tools"

    def draw(self, context):
        ob = self.ob
        cloth = ob.MC_props.cloth
        if cloth:
            sc = bpy.context.scene
            layout = self.layout

            # use current mesh or most recent cloth object if current ob isn't mesh
            MC_data['recent_object'] = ob
            col = layout.column(align=True)
            col.scale_y = 1
            col.label(text='Vertex Groups')
            col.operator('object.mc_vertex_group_pin', text="Pin Selected", icon='PINNED')
            col.prop(ob.MC_props, "vg_pin", text="pin")
            col.prop(ob.MC_props, "vg_drag", text="drag")
            col.prop(ob.MC_props, "vg_surface_follow", text="Surface Follow")



# ^                                                          ^ #
# ^                     END draw code                        ^ #
# ============================================================ #


# testing !!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#install_handler(False)


# testing end !!!!!!!!!!!!!!!!!!!!!!!!!



# ============================================================ #
#                         Register                             #
#                                                              #
def duplication_and_load():
    """Runs in it's own handler for updating objects
    that are duplicated while coth properties are true.
    Also checks for cloth, collider, and target objects
    in the file when blender loads."""
    # for loading no need to check for duplicates because we are regenerating data for everyone
    #if load:
    #    return 0


    #print("running")
    # for detecting duplicates
    obm = False # because deepcopy doesn't work on bmesh
    print("running duplicator")
    cloths = [i for i in bpy.data.objects if i.MC_props.cloth]
    if len(cloths) > 0:
        id = [i['MC_cloth_id'] for i in cloths]
        idx = max(id) + 1
        u, inv, counts = np.unique(id, return_inverse=True, return_counts=True)
        repeated = counts[inv] > 1
        if np.any(repeated):
            dups = np.array(cloths)[repeated]
            for i in dups:
                cloth_instance = MC_data['cloths'][i['MC_cloth_id']]
                cloth_instance.ob = None
                cloth_instance.target = None # objs don't copy with deepcopy
                if 'obm' in dir(cloth_instance):
                    obm = True # objs don't copy with deepcopy
                    cloth_instance.obm = None # objs don't copy with deepcopy
                MC_data['cloths'][idx] = copy.deepcopy(cloth_instance)
                MC_data['cloths'][idx].ob = i # cloth.ob doesn't copy
                MC_data['cloths'][idx].target = i.MC_props.target # cloth.ob doesn't copy

                # not sure if I need to remake the bmesh since it will be remade anyway... Can't duplicate an object in edit mode. If we switch to edit mode it will remake the bmesh.
                #if obm:
                    #MC_data['cloths'][idx].obm = get_bmesh(i) # bmesh doesn't copy

                i['MC_cloth_id'] = idx
                idx += 1

            print("duplicated an object cloth instance here=============")
            # remove the cloth instances that have been copied
            for i in np.unique(np.array(id)[repeated]):
                MC_data['cloths'].pop(i)

    print("finished duplication =====+++++++++++++++++++++++++")
    colliders = [i for i in bpy.data.objects if i.MC_props.cloth]
    return 1


classes = (
    McPropsObject,
    McPropsScene,
    MCResetToBasisShape,
    MCResetSelectedToBasisShape,
    MCSurfaceFollow,
    MCCreateSewLines,
    MCSewToSurface,
    MCCreateVirtualSprings,
    PANEL_PT_modelingClothMain,
    PANEL_PT_modelingClothSettings,
    PANEL_PT_modelingClothSewing,
    PANEL_PT_modelingClothVertexGroups,
    MCVertexGroupPin,
)


def register():
    # classes
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    # props
    bpy.types.Object.MC_props = bpy.props.PointerProperty(type=McPropsObject)
    bpy.types.Scene.MC_props = bpy.props.PointerProperty(type=McPropsScene)

    # clean dead versions of the undo handler
    handler_names = np.array([i.__name__ for i in bpy.app.handlers.undo_post])
    booly = [i == 'undo_frustration' for i in handler_names]
    idx = np.arange(handler_names.shape[0])
    idx_to_kill = idx[booly]
    for i in idx_to_kill[::-1]:
        del(bpy.app.handlers.undo_post[i])
        print("deleted handler ", i)

    # drop in the undo handler
    bpy.app.handlers.undo_post.append(undo_frustration)

    # register the data management timer. Updates duplicated objects and objects with modeling cloth properties
    if False:
        bpy.app.timers.register(duplication_and_load)


def unregister():
    # classes
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)

    # props
    del(bpy.types.Scene.MC_props)
    del(bpy.types.Object.MC_props)

    # clean dead versions of the undo handler
    handler_names = np.array([i.__name__ for i in bpy.app.handlers.undo_post])
    booly = [i == 'undo_frustration' for i in handler_names]
    idx = np.arange(handler_names.shape[0])
    idx_to_kill = idx[booly]
    for i in idx_to_kill[::-1]:
        del(bpy.app.handlers.undo_post[i])


if __name__ == '__main__':
    register()
