"""
Module to download landsat and planet tiles. It needs a list of tiles from
hansen (labels).
"""
import os
import sys
import multiprocessing
import glob
import requests
import logging
from utils import create_dir
from itertools import product

LANDSAT_URLS = {
    '2017': 'https://storage.googleapis.com/landsat-cache/2017/{z}/{x}/{y}.png',
    '2016': 'https://storage.googleapis.com/landsat-cache/2016/{z}/{x}/{y}.png',
    '2015': 'https://storage.googleapis.com/landsat-cache/2015/{z}/{x}/{y}.png',
    '2014': 'https://storage.googleapis.com/landsat-cache/2014/{z}/{x}/{y}.png',
    '2013': 'https://storage.googleapis.com/landsat-cache/2013/{z}/{x}/{y}.png'
}

PLANET_URL = "https://tiles.planet.com/basemaps/v1/planet-tiles/global_quarterly_{year}{q}_mosaic/gmap/{z}/{x}/{y}.png?api_key=25647f4fc88243e2a6e91150aaa117e3"

logger = logging.getLogger('donwload_tiles')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('download_tiles.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

def chunks(l, n):
    """
    Yield successive n-sized chunks from l.
    Params:
        l: list
        n: chunk size
    """
    for i in range(0, len(l), n):
        yield l[i:i + n] # yields a list of size n

def create_tuple(list_, name):
    """
    Create a list of tuple (l_i, name1) for l_i in list
    Params:
        list_: list
        name: second value that we want to add into every tuple
    """
    return [(l, name) for l in list_]

def download_file(url, path):
    """
    Download a file form an url.
    Params:
        url: url of the file to download
        path: path to store the file
        redo: append
    """
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk: # filter out keep-alive new chunks
                        f.write(chunk)
        logger.debug('SUCCESS {} {}'.format(url, path))
        return 1
    except:
         logger.debug('FAIL', url, path)
         return None

def download_tile(tile, out_dir):
    """
    Given a tile coordinate (year, zoom, coord_x, coord_y), download the corresponding
    raw images from planet and landsat.
    Params:
        tile: tuple composed of (year, zoom, x, y)
        out_dir: output directory to store the image
    """
    planet_name = 'pl{year}_{q}_{z}_{x}_{y}.png'
    landsat_name = 'ld{year}_{z}_{x}_{y}.png'
    quarters = ['q1', 'q2', 'q3', 'q4']
    year, z, x, y = tile
    year = int(year)

    # Download Landsat
    landsat_path1 = os.path.join(out_dir, 'landsat', str(year-1), landsat_name.format(year=year-1, z=z, x=x, y=y))
    landsat_path2 = os.path.join(out_dir, 'landsat', str(year), landsat_name.format(year=year, z=z, x=x, y=y))
    if not os.path.exists(landsat_path1) and year!= 2013:
        landsat_url1 = LANDSAT_URLS[str(year-1)].format(z=z, x=x, y=y)
        download_file(landsat_url1, landsat_path1)
    if not os.path.exists(landsat_path2):
        landsat_url2 = LANDSAT_URLS[str(year)].format(z=z, x=x, y=y)
        download_file(landsat_url2, landsat_path2)

    # Download Planet
    for q in quarters:
        if year in [2017, 2018]:
            planet_path1 = os.path.join(out_dir, 'planet', str(year-1), planet_name.format(year=year-1, q=q, z=z, x=x, y=y))
            planet_path2 = os.path.join(out_dir, 'planet', str(year), planet_name.format(year=year, q=q, z=z, x=x, y=y))
            planet_url1 = PLANET_URL.format(year=year-1, q=q, z=z, x=x, y=y)
            planet_url2 = PLANET_URL.format(year=year, q=q, z=z, x=x, y=y)
            if not os.path.exists(planet_path1):
                download_file(planet_url1, planet_path1)
            if not os.path.exists(planet_path2):
                download_file(planet_url2, planet_path2)

def add_in_dict(dic, key):
    """
    Add key in dict if it doesn't exist
    """
    z, x, y = key[0], key[1], key[2]
    if key not in dic:
        dic[key] = {}
        dic[key]['z']= z
        dic[key]['x']= x
        dic[key]['y']= z

def get_tiles(path='/mnt/ds3lab-scratch/lming/gee_data/z11/forest_lossv2'):
    """
    Get the available tiles from the labels (Hansen)
    """
    years = ['2013', '2014', '2015', '2016', '2017', '2018']
    tiles = []
    for year in years:
        year_tiles = glob.glob(os.path.join(path, year, '*.npy'))
        for yt in year_tiles:
            # fl{year}_{z}_{x}_{y}.npy
            tile = yt.split('/')[-1].split('_')
            tiles.append((tile[0][2:], tile[1], tile[2], tile[3][:-4]))
    return tiles

def main():
    zoom = 11
    out_dir = '/mnt/ds3lab-scratch/lming/gee_data/ldpl/video'
    create_dir(out_dir)
    for year in ['2013', '2014', '2015', '2016', '2017']:
        create_dir(os.path.join(out_dir, year))

    for chunk in chunks(tiles, 16):
        with multiprocessing.Pool(processes=16) as pool:
            results = pool.starmap(download_tile, create_tuple(chunk, out_dir))

if __name__ == '__main__':
    main()
