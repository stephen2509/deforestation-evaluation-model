from .base_dataset import BaseVideoDataset
from .base_dataset import VideoDataset, SequenceExampleVideoDataset, VarLenFeatureVideoDataset
from .google_robot_dataset import GoogleRobotVideoDataset
from .sv2p_dataset import SV2PVideoDataset
from .softmotion_dataset import SoftmotionVideoDataset
from .kth_dataset import KTHVideoDataset
from .ucf101_dataset import UCF101VideoDataset
from .cartgripper_dataset import CartgripperVideoDataset
from .planet_dataset import PlanetVideoDataset
from .cropped_dataset import CroppedVideoDataset
from .landsat_dataset import LandsatVideoDataset

def get_dataset_class(dataset):
    dataset_mappings = {
        'google_robot': 'GoogleRobotVideoDataset',
        'sv2p': 'SV2PVideoDataset',
        'softmotion': 'SoftmotionVideoDataset',
        'bair': 'SoftmotionVideoDataset',  # alias of softmotion
        'kth': 'KTHVideoDataset',
        'ucf101': 'UCF101VideoDataset',
        'cartgripper': 'CartgripperVideoDataset',
        'planet': 'PlanetVideoDataset',
        'cropped': 'CroppedVideoDataset',
        'landsat': 'LandsatVideoDataset'
    }
    dataset_class = dataset_mappings.get(dataset, dataset)
    print(dataset_class)
    dataset_class = globals().get(dataset_class)
    if dataset_class is None or not issubclass(dataset_class, BaseVideoDataset):
        raise ValueError('Invalid dataset %s' % dataset)
    return dataset_class
