"""
This module extracts the corresponding tiles of web mercator from a .tif
This .tif file can be obtained from GEE
"""
import os
import glob
import rasterio
import gdal
import numpy as np
import math
import argparse
import matplotlib.pyplot as plt
import pickle as pkl
import logging
from utils import deg2num, num2deg, geodesic2spherical, create_dir
from rasterio.merge import merge
from rasterio.windows import Window
from multiprocessing import Process
# from time import sleep

logger = logging.getLogger('gee')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('gee.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)


def add_in_dict(dic, key):
    """
    Add a new key in the dictionary if it does not exist.
    """
    z, x, y = key[0], key[1], key[2]
    if key not in dic:
        dic[key] = {}
        dic[key]['z']= z
        dic[key]['x']= x
        dic[key]['y']= z

def check_quality_label(img, threshold = 0.01):
    """
    Checks whether the ratio of positive values are greater or equal
    to a given threshold.
    Params:
        img: ndarray
    """
    count_nonzero = np.count_nonzero(img)  # asume BGR, labels in red channel
    img_size = img.size
    if (count_nonzero / img_size) >= threshold:
        return True
    else:
        return False

def bbox2tiles(bbox, zoom):
    """
    Return the tile coordinates that forms a bounding box.
    """
    upper_left_tile = deg2num(bbox['upper_left'][0], bbox['upper_left'][1], zoom)
    lower_right_tile = deg2num(bbox['lower_right'][0], bbox['lower_right'][1], zoom)
    tile_coords = []
    for i in range(upper_left_tile[0], lower_right_tile[0]+1):
        for j in range(upper_left_tile[1], lower_right_tile[1]+1):
            tile_coords.append((zoom, i,j))

    return tile_coords

def extract_tile(mosaicdb, lon, lat, tile_size, crs):
    """
    Extracts a tile of tile_size from a bigger tile.
    Params:
	mosaicdb: Rasterio DataReader
	lon: longitude value in ESPG:4326 or x coordinate in ESPG:3857
	lat: longitude value in ESPG:4326 or y coordinate in ESPG:3857
	tile_size: size of the tile to return
	crs: string, ESPG:4326 or ESPG:3857
    """
    assert crs in ['ESPG:3857', 'ESPG:4326']
    if crs == 'ESPG:4326':
        xgeo, ygeo = geodesic2spherical(lon, lat)
    else:
        xgeo, ygeo = lon, lat
    idx, idy = mosaicdb.index(xgeo, ygeo)
    return mosaicdb.read(window=Window(idy, idx, 256, 256))

def preprocess_fc(img_arr, threshold=0.25):
    """
    Threshold percentage values to be binary with a 0.25 threshold.
    """
    if img_arr.max() == 100.:
        img_arr = img_arr / 100.
    fc_mask = np.where(img_arr >= threshold)
    nfc_mask = np.where(img_arr < threshold)
    img_arr[fc_mask] = 1
    img_arr[nfc_mask] = 0
    return img_arr

def create_forest_cover(fc2000, gain2000_2012, loss2000_2012, loss2013_year):
    """
    Create forest cover the specified year. For gain and loss on the same pixel
    between 2000-2012, we assume that nothing happened.
    Params:
        fc2000: ndarray binary mask. Forest cover from 2000.
        gain2000_2012: ndarray binary mask. Forest gain from 2000 to 2012.
        loss2000_2012: ndarray binary mask. Forest loss from 2000 to 2012.
        loss2013_year: ndarray binary mask. Forest loss from 2013 to year.
    """
    gain_loss2000_2012 = gain2000_2012 - loss2000_2012 # 0 if loss and gain, 1 if only gain, -1 if only loss
    gain_mask = np.where(gain_loss2000_2012==1)
    loss_mask = np.where(gain_loss2000_2012==-1)
    loss2013_year_mask = np.where(loss2013_year==1)
    # Update forest cover
    fc2000[gain_mask] = 1
    fc2000[loss_mask] = 0
    fc2000[loss2013_year_mask] = 0
    return fc2000

def get_aggregated_loss(img_arr, beg=1, end=12):
    """
    Gets the forest total loss from 2001 to 2012.
    """
    loss_arr = np.zeros(img_arr.shape)
    for i in range(beg, end+1): # +1 because range is exclusive
        mask = np.where(img_arr==i)
        loss_arr[mask] = 1
    return loss_arr

def save_fc(img_arr, out_name, year):
    """
    img_arr: hansen db
    out_name: full path of the forest loss name
    year: to extract
    """
    FC_IDX = 0 # forest cover index
    gee_dir = '/mnt/ds3lab-scratch/lming/gee_data/images_forma_compare'
    GAIN_IDX = 1 # forest gain index
    LOSS_IDX = 2 # forest loss index
    # loss_arr = extract_tile(img_db[LOSS_IDX], lon, lat, 256, crs='ESPG:4326')
    loss_arr = np.copy(img_arr[LOSS_IDX])
    loss2000_2012 = get_aggregated_loss(loss_arr, beg=1, end=12) # 0 is no loss in this band, get loss from [1,12]
    # gain2000_2012 = extract_tile(img_db[GAIN_IDX])
    gain2000_2012 = np.copy(img_arr[GAIN_IDX])
    loss2013_year = get_aggregated_loss(loss_arr, beg=13, end=year)
    # fc2000 = extract_tile(img_db[FC_IDX], lon, lat, 256, crs='ESPG:4326')
    fc2000 = np.copy(img_arr[FC_IDX])
    fc2000 = preprocess_fc(fc2000)
    img_arr = create_forest_cover(fc2000, gain2000_2012, loss2000_2012, loss2013_year)

    forest_cover_dir = os.path.join(gee_dir, 'forest_coverv2', '20' + str(year))
    create_dir(forest_cover_dir)

    fl_name = out_name.split('/')[-1]
    fc_name = 'fc' + '20' + str(year) + '_' + '_'.join(fl_name.split('_')[1:])
    fc_name = os.path.join(forest_cover_dir, fc_name)
    np.save(fc_name, img_arr)

def gen_tile(img_db, lon, lat, year, out_name):
    """
    year: int, from 1 to 18
    """
    # 'treecover2000', 'gain', 'lossyear', 'lossyear2000_2012')
    FC_IDX = 0 # forest cover index
    GAIN_IDX = 1 # forest gain index
    LOSS_IDX = 2 # forest loss index
    img_arr = extract_tile(img_db, lon, lat, 256, crs='ESPG:4326')
    if img_arr.size == 0:
        print('WARNING:', out_name)
    img_arr = np.copy(img_arr[LOSS_IDX])
    loss_mask = np.where(img_arr == year)
    no_loss_mask = np.where(img_arr != year)
    img_arr[loss_mask] = 1
    img_arr[no_loss_mask] = 0
    if check_quality_label(img_arr):
        np.save(out_name, img_arr)
        save_fc(img_arr, out_name, year)

def extract_fc_and_fl_tile(img_db, lon, lat, year, out_name):
    """
    year: int, from 1 to 18
    """
    # 'treecover2000', 'gain', 'lossyear', 'lossyear2000_2012')
    FC_IDX = 0 # forest cover index
    GAIN_IDX = 1 # forest gain index
    LOSS_IDX = 2 # forest loss index
    img_arr = extract_tile(img_db, lon, lat, 256, crs='ESPG:4326')
    if img_arr.size == 0:
        print('WARNING:', out_name)
    img_arr_loss = np.copy(img_arr[LOSS_IDX])
    loss_mask = np.where(img_arr_loss == year)
    no_loss_mask = np.where(img_arr_loss != year)
    img_arr_loss[loss_mask] = 1
    img_arr_loss[no_loss_mask] = 0
    print(img_arr_loss.shape)
    np.save(out_name, img_arr_loss)
    # save_fc(img_arr, out_name, year)

def extract_tiles(tiles, year, hansen_db, forest_loss_dir):
    out_fl = os.path.join(forest_loss_dir, year)
    create_dir(out_fl)
    fl_template = 'fl{year}_{z}_{x}_{y}.npy'
    # for z,x,y in [(12, 1260, 2185)]:
    for z, x, y in tiles:
        lon, lat = num2deg(int(x), int(y), int(z))
        int_year = int(year[2:])
        # gen_tile(landsat_db, lon, lat, 'ld', int_year, os.path.join(out_landsat, landsat_template.format(year=year, z=z, x=x, y=y)))
        # gen_tile(hansen_db, lon, lat, 'fc', int_year, os.path.join(out_fc, fc_template.format(year=year, z=z, x=x, y=y)))
        gen_tile(hansen_db, lon, lat, int_year, os.path.join(out_fl, fl_template.format(year=year, z=z, x=x, y=y)))


###
def get_tiles(path='/mnt/ds3lab-scratch/lming/gee_data/z11/forest_lossv2'):
    """
    Get tiles from labels (Hansen)
    """
    # years = ['2013', '2014', '2015', '2016', '2017']
    years = ['2016_1', '2016']
    tiles = []
    for year in years:
        year_tiles = glob.glob(os.path.join(path, year, '*.npy'))
        for yt in year_tiles:
            # fl{year}_{z}_{x}_{y}.npy
            tile = yt.split('/')[-1].split('_')
            key = (tile[1], tile[2], tile[3][:-4])
            add_in_dict(tiles, key)
    return list(tiles.keys())

def extract_video_tiles(tiles, year, hansen_db, forest_loss_dir):
    out_fl = os.path.join(forest_loss_dir, year)
    create_dir(out_fl)
    fl_template = 'fl{year}_{z}_{x}_{y}.npy'
    # for z,x,y in [(12, 1260, 2185)]:
    for z, x, y in tiles:
        lon, lat = num2deg(int(x), int(y), int(z))
        int_year = int(year[2:])
        extract_fc_and_fl_tile(hansen_db, lon, lat, int_year, os.path.join(out_fl, fl_template.format(year=year, z=z, x=x, y=y)))

def extract_forma_tiles(tiles, year, hansen_db, forest_loss_dir):
    # TODO: CHANGE SAVE_FC SAVING MODE!!!!!!!
    out_fl = os.path.join(forest_loss_dir, year)
    create_dir(out_fl)
    fl_template = 'fl{year}_{z}_{x}_{y}.npy'
    for z, x, y in tiles:
        out_name = os.path.join(out_fl, fl_template.format(year=year, z=z, x=x, y=y))
        lon, lat = num2deg(int(x), int(y), int(z))
        int_year = int(year[2:])
        # img_arr = extract_tile(hansen_db, lon, lat, 256, crs='ESPG:4326')
        # np.save(os.path.join(forest_loss_dir, fl_template.format(year=year, z=z, x=x, y=y)), img_arr)
        # save_fc(img_arr, out_name, int_year)

        extract_fc_and_fl_tile(hansen_db, lon, lat, int_year, os.path.join(out_fl, fl_template.format(year=year, z=z, x=x, y=y)))

def main():
    gee_dir = '/mnt/ds3lab-scratch/lming/gee_data/images_forma_compare'
    # landsat_db_dir = os.path.join(gee_dir, 'ls7')

    bbox = {
		'upper_left': (-84.04511825722398, 13.898213869443307),
		'lower_right': (-38.082088, -52.993502)
    }
    zoom = 11
    # tiles = bbox2tiles(bbox, zoom)
    # with open('/mnt/ds3lab-scratch/lming/gee_data/forma_tiles2017.pkl', 'rb') as f:
    #     tiles = pkl.load(f)
    tiles = [('11','753','1076'), ('11','773','1071')]

    forest_cover_dir = os.path.join(gee_dir, 'forest_coverv2')
    forest_loss_dir = os.path.join(gee_dir, 'forest_lossv2')
    forest_cover_dir = gee_dir
    forest_loss_dir = gee_dir
    # landsat_dir = os.path.join(gee_dir, 'ls7', 'processed')
    create_dir(forest_cover_dir)
    create_dir(forest_loss_dir)
    # years = ['2013', '2014', '2015', '2016', '2017', '2018']
    years = ['2016', '2017']
    # landsat_dbs = {}
    for year in years:
        create_dir(os.path.join(forest_cover_dir, year))
        create_dir(os.path.join(forest_loss_dir, year))
        # create_dir(os.path.join(landsat_dir, year))
        # landsat_dbs[year] = rasterio.open(os.path.join(landsat_db_dir, 'landsat' + year + '.vrt'))
    hansen_db = rasterio.open('/mnt/ds3lab-scratch/lming/gee_data/hansen11.vrt')

    processes = []
    for year in years:
        # p = Process(target=extract_tiles, args=(tiles, year, hansen_db,
        #         forest_loss_dir,))
        # p = Process(target=extract_video_tiles, args=(tiles, year, hansen_db, forest_loss_dir))
        p = Process(target=extract_forma_tiles, args=(tiles, year, hansen_db, forest_loss_dir))
        processes.append(p)
        p.start()
    for p in processes:
        p.join()

if __name__ == '__main__':
    main()
