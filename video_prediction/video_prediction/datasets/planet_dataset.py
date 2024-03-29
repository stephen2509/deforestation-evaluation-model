import argparse
import glob
import itertools
import os
import pickle
import random
import re

import numpy as np
import skimage.io
import tensorflow as tf

from video_prediction.datasets.base_dataset import VarLenFeatureVideoDataset


class PlanetVideoDataset(VarLenFeatureVideoDataset):
    def __init__(self, *args, **kwargs):
        super(PlanetVideoDataset, self).__init__(*args, **kwargs)
        from google.protobuf.json_format import MessageToDict
        example = next(tf.python_io.tf_record_iterator(self.filenames[0]))
        dict_message = MessageToDict(tf.train.Example.FromString(example))
        feature = dict_message['features']['feature']
        image_shape = tuple(int(feature[key]['int64List']['value'][0]) for key in ['height', 'width', 'channels'])
        self.state_like_names_and_shapes['images'] = 'images/encoded', image_shape

    def get_default_hparams_dict(self):
        default_hparams = super(PlanetVideoDataset, self).get_default_hparams_dict()
        hparams = dict(
            context_frames=1,
            sequence_length=4,
            # clip_length=1,
            # long_sequence_length=4,
            # force_time_shift=True,
            # shuffle_on_val=True,
            use_state=False,
        )
        return dict(itertools.chain(default_hparams.items(), hparams.items()))

    @property
    def jpeg_encoding(self):
        return False

    def num_examples_per_epoch(self):
        with open(os.path.join(self.input_dir, 'sequence_lengths.txt'), 'r') as sequence_lengths_file:
            sequence_lengths = sequence_lengths_file.readlines()
        sequence_lengths = [int(sequence_length.strip()) for sequence_length in sequence_lengths]
        return np.sum(np.array(sequence_lengths) >= self.hparams.sequence_length)


def _bytes_feature(value):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def _bytes_list_feature(values):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=values))


def _int64_feature(value):
    return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))


def add_in_dict(dic, key, q, data):

    if key in dic:
        dic[key][q] = data
    else:
        dic[key] = {q: data}

# TODO: put in utils
def get_tile_info(tile):
    """
    Retrieve the year, zoom, x, y from a tile. Example: 2017_12_1223_2516.png
    """
    tile_name = tile.split('/')[-1]
    tile_items = tile_name.split('_')

    year = tile_items[0][2:]
    q = tile_items[1]
    z = tile_items[2]
    x = tile_items[3]
    y = tile_items[4][:-4]
    return year, q, z, x, y

def def_dic(img_dir, year, z, x, y):
    ntemp = os.path.join(img_dir, 'pl{year}_{q}_{z}_{x}_{y}.png')
    dic = {
            str(year-1): {
                'q1': ntemp.format(year=year-1, q='q1', z=z, x=x, y=y),
                'q2': ntemp.format(year=year-1, q='q2', z=z, x=x, y=y),
                'q3': ntemp.format(year=year-1, q='q3', z=z, x=x, y=y),
                'q4': ntemp.format(year=year-1, q='q4', z=z, x=x, y=y)
            },
            str(year): {
                'q1': ntemp.format(year=year, q='q1', z=z, x=x, y=y),
                'q2': ntemp.format(year=year, q='q2', z=z, x=x, y=y),
                'q3': ntemp.format(year=year, q='q3', z=z, x=x, y=y),
                'q4': ntemp.format(year=year, q='q4', z=z, x=x, y=y)
            }
    }
    return dic

def add_img(dic, img_dir, year, q, z, x, y):
    # if 2016, 2017 is guaranteed
    # if 2017, 2016 is not guaranteed, 2018 is not guaranteed, but one of them is
    # if 2018, 2017 is guaranteed
    key = None
    if year == '2016':
        key = '_'.join(('2017', z, x, y))
        year = '2017'
    elif year == '2018':
        key = '_'.join(('2018', z, x, y))
    if key:
        if key not in dic:
            dic[key] = def_dic(img_dir, int(year), z, x, y)

def get_imgs(img_dir, limit=5000):
    data = {}
    img_paths = glob.glob(os.path.join(img_dir, '*'))
    for path in img_paths:
        year, q, z, x, y = get_tile_info(path)
        add_img(data, img_dir, year, q, z, x, y)
        if len(data) >= limit:
            break
    return data

"""
def get_imgs(img_dir, limit=5000):

    return: {
        12_10_10: img1, img2, img3
    }
    
    data = {}
    img_paths = glob.glob(os.path.join(img_dir, '*'))
    for path in img_paths:
        year, q, z, x, y = get_tile_info(path)
        key = '_'.join((z, x, y))
        add_in_dict(data, key, '_'.join((year,q)), path)
    keys = list(data.keys())
    new_data = {}
    assert limit < len(keys)
    for i in range(limit):
        key = keys[i]
        new_data[key] = data[key]
    print('IMAGES RETURN', len(new_data))
    return new_data
"""

def save_tf_record(output_fname, sequences):
    print('saving sequences to %s' % output_fname)
    with tf.python_io.TFRecordWriter(output_fname) as writer:
        for sequence in sequences:
            num_frames = len(sequence) # 6, 2 years
            height, width, channels = sequence[0].shape
            encoded_sequence = [image.tostring() for image in sequence]
            features = tf.train.Features(feature={
                'sequence_length': _int64_feature(num_frames),
                'height': _int64_feature(height),
                'width': _int64_feature(width),
                'channels': _int64_feature(channels),
                'images/encoded': _bytes_list_feature(encoded_sequence),
            })
            example = tf.train.Example(features=features)
            writer.write(example.SerializeToString())

def get_quad_list(key, quad):
    info = key.split('_')
    year, z, x, y = int(info[0]), info[1], info[2], info[3]
    
    return [
        quad[str(year-1)]['q1'],
        quad[str(year-1)]['q2'],
        quad[str(year-1)]['q3'],
        quad[str(year-1)]['q4'],
        quad[str(year)]['q1'],
        quad[str(year)]['q2'],
        quad[str(year)]['q3'],
        quad[str(year)]['q4']
    ]

def read_frames_and_save_tf_records(output_dir, img_quads, image_size, sequences_per_file=128):
    """
    img_quads: {
        key1: {year_q1: img1, year_q2: img2, year_q3: img3}
        key2: {year_q1: img1, year_q2: img2, year_q3: img3}
    }
    """
    partition_name = os.path.split(output_dir)[1]

    sequences = []
    sequence_iter = 0
    sequence_lengths_file = open(os.path.join(output_dir, 'sequence_lengths.txt'), 'w')
    for video_iter, key in enumerate(img_quads.keys()):
        frame_fnames = get_quad_list(key, img_quads[key])
        # frame_fnames = [quads['q1'], quads['q2'], quads['q3'], quads['q4']]
        frames = skimage.io.imread_collection(frame_fnames)
        frames = [frame[:,:,:3] for frame in frames] # take only RGB
        if not sequences:
            last_start_sequence_iter = sequence_iter
            print("reading sequences starting at sequence %d" % sequence_iter)
        sequences.append(frames)
        sequence_iter += 1
        sequence_lengths_file.write("%d\n" % len(frames)) # should be always 3
        if (len(sequences) == sequences_per_file or
                (video_iter == (len(img_quads) - 1))):
            output_fname = 'sequence_{0}_to_{1}.tfrecords'.format(last_start_sequence_iter, sequence_iter - 1)
            output_fname = os.path.join(output_dir, output_fname)
            save_tf_record(output_fname, sequences)
            sequences[:] = []
    sequence_lengths_file.close()

def part_dict(dic, num):
    total = len(dic)
    assert num < total
    rest = total - num
    dic1 = {}
    dic2 = {}
    itr = 0
    for key, value in dic.items():
        if itr < num:
            dic1[key] = value
        else:
            dic2[key] = value
        itr = itr + 1
    return dic1, dic2

def partition_data(quads):
    total_quads = len(quads)
    num_train = int(0.8 * total_quads)
    num_val = int(0.1 * total_quads)
    print('===', num_train, num_val)
    train_quads, test_quads = part_dict(quads, num_train)
    train_quads, val_quads = part_dict(train_quads, num_train - num_val)
    return [train_quads, val_quads, test_quads]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str, help="directory containing the quarter mosaics from planet")
    parser.add_argument("output_dir", type=str)
    parser.add_argument("image_size", type=int)
    args = parser.parse_args()

    partition_names = ['train', 'val', 'test']
    quads = get_imgs(args.input_dir)
#     train_quads, val_quads, test_quads
    quad_list = partition_data(quads)
    print(len(quad_list[0]), len(quad_list[1]), len(quad_list[2]))
    for partition_name, partition_quad in zip(partition_names, quad_list):
    # for partition_name, partition_fnames in zip(partition_names, partition_fnames):
        partition_dir = os.path.join(args.output_dir, partition_name)
        if not os.path.exists(partition_dir):
            os.makedirs(partition_dir)
        read_frames_and_save_tf_records(partition_dir, partition_quad, args.image_size)


if __name__ == '__main__':
    main()

# def partition_data(input_dir):
#     # List files and corresponding person IDs
#     fnames = glob.glob(os.path.join(input_dir, '*/*'))
#     fnames = glob.glob(os.path.join(input_dir, '*'))
#     fnames = [fname for fname in fnames if os.path.isdir(fname)]
#     mosaics = []
#     persons = [re.match('person(\d+)_\w+_\w+', os.path.split(fname)[1]).group(1) for fname in fnames]
#     persons = np.array([int(person) for person in persons])
#
#     train_mask = persons <= 16
#
#     train_fnames = [fnames[i] for i in np.where(train_mask)[0]]
#     test_fnames = [fnames[i] for i in np.where(~train_mask)[0]]
#
#     random.shuffle(train_fnames)
#
#     pivot = int(0.95 * len(train_fnames))
#     train_fnames, val_fnames = train_fnames[:pivot], train_fnames[pivot:]
#     return train_fnames, val_fnames, test_fnames

# def save_tf_record(output_fname, sequences):
#     print('saving sequences to %s' % output_fname)
#     with tf.python_io.TFRecordWriter(output_fname) as writer:
#         for sequence in sequences:
#             num_frames = len(sequence)
#             height, width, channels = sequence[0].shape
#             encoded_sequence = [image.tostring() for image in sequence]
#             features = tf.train.Features(feature={
#                 'sequence_length': _int64_feature(num_frames),
#                 'height': _int64_feature(height),
#                 'width': _int64_feature(width),
#                 'channels': _int64_feature(channels),
#                 'images/encoded': _bytes_list_feature(encoded_sequence),
#             })
#             example = tf.train.Example(features=features)
#             writer.write(example.SerializeToString())

# def read_frames_and_save_tf_records(output_dir, video_dirs, image_size, sequences_per_file=128):
#     # I can do 2 years: 2016_q1, q2, q3, 2017_q1, q2, q3
#     partition_name = os.path.split(output_dir)[1]
#
#     sequences = []
#     sequence_iter = 0
#     sequence_lengths_file = open(os.path.join(output_dir, 'sequence_lengths.txt'), 'w')
#     for video_iter, video_dir in enumerate(video_dirs):
#         meta_partition_name = partition_name if partition_name == 'test' else 'train'
#         meta_fname = os.path.join(os.path.split(video_dir)[0], '%s_meta%dx%d.pkl' %
#                                   (meta_partition_name, image_size, image_size))
#         with open(meta_fname, "rb") as f:
#             data = pickle.load(f)
#
#         vid = os.path.split(video_dir)[1]
#         (d,) = [d for d in data if d['vid'] == vid]
#         for frame_fnames_iter, frame_fnames in enumerate(d['files']):
#             frame_fnames = [os.path.join(video_dir, frame_fname) for frame_fname in frame_fnames]
#             frames = skimage.io.imread_collection(frame_fnames)
#             # they are grayscale images, so just keep one of the channels
#             frames = [frame[..., 0:1] for frame in frames]
#
#             if not sequences:
#                 last_start_sequence_iter = sequence_iter
#                 print("reading sequences starting at sequence %d" % sequence_iter)
#
#             sequences.append(frames)
#             sequence_iter += 1
#             sequence_lengths_file.write("%d\n" % len(frames))
#
#             if (len(sequences) == sequences_per_file or
#                     (video_iter == (len(video_dirs) - 1) and frame_fnames_iter == (len(d['files']) - 1))):
#                 output_fname = 'sequence_{0}_to_{1}.tfrecords'.format(last_start_sequence_iter, sequence_iter - 1)
#                 output_fname = os.path.join(output_dir, output_fname)
#                 save_tf_record(output_fname, sequences)
#                 sequences[:] = []
#     sequence_lengths_file.close()
