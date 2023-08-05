# -*- coding: utf-8 -*-
"""unet_resnet34_final.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/16zYVYfvkXxZZ_5uOkxxjGTpWxT_-rU48
"""

import os
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

import numpy as np
import cv2
import matplotlib.pyplot as plt
import albumentations as albu
import torch
from torch.utils.data import DataLoader
from torch.utils.data import Dataset as BaseDataset
import seg_mp as smp
from seg_mp import utils as smp_util

DATA_DIR = '../testdata/Custom_Dataset_736_960'

# helper function for data visualization
def visualize(**images):
    n = len(images)
    plt.figure(figsize=(16, 5))
    for i, (name, image) in enumerate(images.items()):
        plt.subplot(1, n, i + 1)
        plt.xticks([])
        plt.yticks([])
        plt.title(' '.join(name.split('_')).title())
        plt.imshow(image)
    plt.show()

"""### Dataloader

Writing helper class for data extraction, tranformation and preprocessing  
https://pytorch.org/docs/stable/data
"""

class Dataset(BaseDataset):
    CLASSES = ['sky', 'building', 'pole', 'road', 'pavement', 
               'tree', 'signsymbol', 'fence', 'car', 
               'pedestrian', 'bicyclist', 'unlabelled']
    
    def __init__(
            self, 
            images_dir, 
            masks_dir, 
            classes=None, 
            augmentation=None, 
            preprocessing=None,
    ):
        self.ids = os.listdir(images_dir)
        self.images_fps = [os.path.join(images_dir, image_id) for image_id in self.ids]
        self.masks_fps = [os.path.join(masks_dir, image_id) for image_id in self.ids]
        
        # convert str names to class values on masks
        self.class_values = [self.CLASSES.index(cls.lower()) for cls in classes]
        
        self.augmentation = augmentation
        self.preprocessing = preprocessing
    
    def __getitem__(self, i):
        
        # read data
        image = cv2.imread(self.images_fps[i])
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(self.masks_fps[i], 0)
        
        # extract certain classes from mask (e.g. cars)
        masks = [(mask == v) for v in self.class_values]
        mask = np.stack(masks, axis=-1).astype('float')
        
        # apply augmentations
        if self.augmentation:
            sample = self.augmentation(image=image, mask=mask)
            image, mask = sample['image'], sample['mask']
        
        # apply preprocessing
        if self.preprocessing:
            sample = self.preprocessing(image=image, mask=mask)
            image, mask = sample['image'], sample['mask']
            
        return image, mask
        
    def __len__(self):
        return len(self.ids)

def get_training_augmentation():
    train_transform = [

        albu.HorizontalFlip(p=0.5),

        albu.ShiftScaleRotate(scale_limit=0.5, rotate_limit=0, shift_limit=0.1, p=1, border_mode=0),

        albu.PadIfNeeded(min_height=320, min_width=320, always_apply=True, border_mode=0),
        albu.RandomCrop(height=320, width=320, always_apply=True),

        albu.IAAAdditiveGaussianNoise(p=0.2),
        albu.IAAPerspective(p=0.5),

        albu.OneOf(
            [
                albu.CLAHE(p=1),
                albu.RandomBrightness(p=1),
                albu.RandomGamma(p=1),
            ],
            p=0.9,
        ),

        albu.OneOf(
            [
                albu.IAASharpen(p=1),
                albu.Blur(blur_limit=3, p=1),
                albu.MotionBlur(blur_limit=3, p=1),
            ],
            p=0.9,
        ),

        albu.OneOf(
            [
                albu.RandomContrast(p=1),
                albu.HueSaturationValue(p=1),
            ],
            p=0.9,
        ),
    ]
    return albu.Compose(train_transform)


def get_validation_augmentation():
    test_transform = [
        albu.PadIfNeeded(384, 480)
    ]
    return albu.Compose(test_transform)


def to_tensor(x, **kwargs):
    return x.transpose(2, 0, 1).astype('float32')


def get_preprocessing(preprocessing_fn):
    _transform = [
        albu.Lambda(image=preprocessing_fn),
        albu.Lambda(image=to_tensor, mask=to_tensor),
    ]
    return albu.Compose(_transform)

ENCODER = 'resnet34'
ENCODER_WEIGHTS = 'imagenet'
CLASSES = ['sky', 'building', 'pole', 'road', 'pavement', 
               'tree', 'signsymbol', 'fence', 'car', 
               'pedestrian', 'bicyclist', 'unlabelled']
ACTIVATION = 'sigmoid'
DEVICE = 'cuda'

preprocessing_fn = smp.encoders.get_preprocessing_fn(ENCODER, ENCODER_WEIGHTS)

loss = smp_util.losses.DiceLoss()
metrics = [
    smp_util.metrics.IoU(threshold=0.5),
]

"""## Test best saved model"""

# load best saved checkpoint
best_model = torch.load('./model/unet_resnet34_model.pth')

# create test dataset
x_test_day_dir = os.path.join(DATA_DIR, 'day')
y_test_day_dir = os.path.join(DATA_DIR, 'label')

test_dataset_day = Dataset(
    x_test_day_dir, 
    y_test_day_dir, 
    augmentation=get_validation_augmentation(), 
    preprocessing=get_preprocessing(preprocessing_fn),
    classes=CLASSES,
)

x_test_night_dir = os.path.join(DATA_DIR, 'night')
y_test_night_dir = os.path.join(DATA_DIR, 'label')

test_dataset_night = Dataset(
    x_test_night_dir, 
    y_test_night_dir, 
    augmentation=get_validation_augmentation(), 
    preprocessing=get_preprocessing(preprocessing_fn),
    classes=CLASSES,
)

"""## Visualize predictions"""

# test dataset without transformations for image visualization
test_day_dataset_vis = Dataset(
    x_test_day_dir, y_test_day_dir, 
    classes=CLASSES,
)

test_night_dataset_vis = Dataset(
    x_test_night_dir, y_test_night_dir, 
    classes=CLASSES,
)

def iou(pred1, pred2):
  iou_score=0
  for i in (0,1,3,5,6,8,9):
    intersection = np.logical_and(pred1[i,:,:], pred2[i,:,:])
    union = np.logical_or(pred1[i,:,:], pred2[i,:,:])
    if np.sum(union)!=0:
      iou_score += np.sum(intersection) / np.sum(union)
  return iou_score

def dice_coef(mask1, mask2, smooth=1):
  dice=0
  for i in (0,1,3,5,6,8,9):
    mask1[i,:,:].squeeze()
    mask2[i,:,:].squeeze
    intersect = np.sum(mask1[i,:,:]*mask2[i,:,:])
    fsum = np.sum(mask1[i,:,:])
    ssum = np.sum(mask2[i,:,:])
    dice_temp = 0
    if (fsum + ssum)!=0:
      dice_temp = (2 * intersect ) / (fsum + ssum)
    dice_temp = np.mean(dice_temp)
    dice += round(dice_temp, 3)
  return dice

def merge_mask(masks):
  mask = masks[0].copy()*28
  mask = mask+masks[1]*56
  for i in (3,5,6,8,9):
    mask=mask+(masks[i]*28*i)
  return mask

def output_pred(daypred, nightpred,i):
  cv2.imwrite("./DayPred/"+os.listdir(x_test_night_dir)[i],daypred)
  cv2.imwrite("./NightPred/"+os.listdir(x_test_night_dir)[i],nightpred)

iou_score = 0
dice_score = 0
dataset_len = len(test_dataset_day)
for i in range(dataset_len):
    image_vis_day = test_day_dataset_vis[i][0].astype('uint8')
    image_vis_night = test_night_dataset_vis[i][0].astype('uint8')
    image_day, gt_mask_day = test_dataset_day[i]
    image_night, gt_mask_night = test_dataset_night[i]
    x_tensor = torch.from_numpy(image_day).to(DEVICE).unsqueeze(0)
    pr_mask_day = best_model.predict(x_tensor)
    pr_mask_day = (pr_mask_day.squeeze().cpu().numpy().round())
    x_tensor = torch.from_numpy(image_night).to(DEVICE).unsqueeze(0)
    pr_mask_night = best_model.predict(x_tensor)
    pr_mask_night = (pr_mask_night.squeeze().cpu().numpy().round())
    iou_score += iou(pr_mask_day, pr_mask_night)
    dice_score += dice_coef(pr_mask_day, pr_mask_night)
    output_pred(merge_mask(pr_mask_day),merge_mask(pr_mask_night),i)
print("IOU (Day vs Night): ", iou_score/dataset_len)
print("Dice (Day vs Night): ", dice_score/dataset_len)