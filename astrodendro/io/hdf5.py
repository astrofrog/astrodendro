# Computing Astronomical Dendrograms
# Copyright (c) 2011-2012 Thomas P. Robitaille and Braden MacDonald
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import numpy as np

# Helper functions:


def _parse_newick(string):

    items = {}

    # Find maximum level
    current_level = 0
    max_level = 0
    for i, c in enumerate(string):
        if c == '(':
            current_level += 1
        if c == ')':
            current_level -= 1
        max_level = max(max_level, current_level)

    # Loop through levels and construct tree
    for level in range(max_level, 0, -1):

        pairs = []

        current_level = 0
        for i, c in enumerate(string):
            if c == '(':
                current_level += 1
                if current_level == level:
                    start = i
            if c == ')':
                if current_level == level:
                    pairs.append((start, i))
                current_level -= 1

        for pair in pairs[::-1]:

            # Extract start and end of branch definition
            start, end = pair

            # Find the ID of the branch
            colon = string.find(":", end)
            branch_id = string[end + 1:colon]
            if branch_id == '':
                branch_id = 'trunk'
            else:
                branch_id = int(branch_id)

            # Add branch definition to overall definition
            items[branch_id] = eval("{%s}" % string[start + 1:end])

            # Remove branch definition from string
            string = string[:start] + string[end + 1:]

    new_items = {}

    def collect(d):
        for item in d:
            if item in items:
                collect(items[item])
                d[item] = (items[item], d[item])
        return

    collect(items['trunk'])

    return items['trunk']

# Import and export


def dendro_export_hdf5(d, filename):
    """Export the dendrogram 'd' to the HDF5 file 'filename'"""
    import h5py
    f = h5py.File(filename, 'w')

    f.attrs['n_dim'] = d.n_dim

    f.create_dataset('newick', data=d.to_newick())

    ds = f.create_dataset('index_map', data=d.index_map, compression=True)
    ds.attrs['CLASS'] = 'IMAGE'
    ds.attrs['IMAGE_VERSION'] = '1.2'
    ds.attrs['IMAGE_MINMAXRANGE'] = [d.index_map.min(), d.index_map.max()]

    ds = f.create_dataset('data', data=d.data, compression=True)
    ds.attrs['CLASS'] = 'IMAGE'
    ds.attrs['IMAGE_VERSION'] = '1.2'
    ds.attrs['IMAGE_MINMAXRANGE'] = [d.data.min(), d.data.max()]

    f.close()


def dendro_import_hdf5(filename):
    """Import 'filename' and construct a dendrogram from it"""
    import h5py
    from ..dendrogram import Dendrogram
    from ..structure import Structure
    h5f = h5py.File(filename, 'r')
    d = Dendrogram()
    d.n_dim = h5f.attrs['n_dim']
    d.data = h5f['data'].value
    d.index_map = h5f['index_map'].value
    d.nodes_dict = {}

    flux_by_node = {}
    indices_by_node = {}

    def _construct_tree(repr):
        nodes = []
        for idx in repr:
            node_indices = indices_by_node[idx]
            f = flux_by_node[idx]
            if type(repr[idx]) == tuple:
                sub_nodes_repr = repr[idx][0]  # Parsed representation of sub nodes
                sub_nodes = _construct_tree(sub_nodes_repr)
                for i in sub_nodes:
                    d.nodes_dict[i.idx] = i
                b = Structure(node_indices, f, children=sub_nodes, idx=idx)
                # Correct merge levels - complicated because of the
                # order in which we are building the tree.
                # What we do is look at the heights of this branch's
                # 1st child as stored in the newick representation, and then
                # work backwards to compute the merge level of this branch
                first_child_repr = sub_nodes_repr.itervalues().next()
                if type(first_child_repr) == tuple:
                    height = first_child_repr[1]
                else:
                    height = first_child_repr
                d.nodes_dict[idx] = b
                nodes.append(b)
            else:
                l = Structure(node_indices, f, idx=idx)
                nodes.append(l)
                d.nodes_dict[idx] = l
        return nodes

    # Do a fast iteration through d.data, adding the indices and data values
    # to the two dictionaries declared above:
    indices = np.indices(d.data.shape).reshape(d.data.ndim, np.prod(d.data.shape)).transpose()

    for coord in indices:
        coord = tuple(coord)
        idx = d.index_map[coord]
        if idx:
            try:
                flux_by_node[idx].append(d.data[coord])
                indices_by_node[idx].append(coord)
            except KeyError:
                flux_by_node[idx] = [d.data[coord]]
                indices_by_node[idx] = [coord]

    d.trunk = _construct_tree(_parse_newick(h5f['newick'].value))
    # To make the node.level property fast, we ensure all the items in the
    # trunk have their level cached as "0"
    for node in d.trunk:
        node._level = 0  # See the @property level() definition in structure.py

    return d
