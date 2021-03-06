"""
Functions used to process and augment video data prior to passing into a model to train. 
Additionally also processing all bounding boxes in a video according to the transformations performed on the video.

Usage:
    In a custom dataset class:
    from preprocessing_transforms import *

clip: Input to __call__ of each transform is a list of PIL images

All functions have an example in the TestPreproc class at the bottom of this file
"""

import torch
import torchvision
from torchvision.transforms import functional as F
from PIL import Image
from PIL import ImageChops
import cv2
from scipy import ndimage
import numpy as np
from abc import ABCMeta
from math import floor, ceil

class PreprocTransform(object):
    """
    Abstract class for preprocessing transforms that contains methods to convert clips to PIL images.
    """
    __metaclass__ = ABCMeta
    def __init__(self, **kwargs):
        pass

    def __init__(self, *args, **kwargs):
        pass

    def _to_pil(self, clip):
        # Must be of type uint8 if images have multiple channels, int16, int32, or float32 if there is only one channel
        if isinstance(clip[0], np.ndarray):
            if 'float' in str(clip[0].dtype):
                clip = np.array(clip).astype('float32')
            if 'int64' == str(clip[0].dtype):
                clip = np.array(clip).astype('int32')
            if clip[0].ndim == 3:
                clip = np.array(clip).astype('uint8')

        output=[]
        for frame in clip:
            output.append(F.to_pil_image(frame))
        
        return output


    def _to_numpy(self, clip):
        output = []
        if isinstance(clip[0], torch.Tensor):
            if isinstance(clip, torch.Tensor):
                output = clip.numpy()
            else:
                for frame in clip:
                    f_shape = frame.shape
                    # Convert from torch's C, H, W to numpy H, W, C
                    frame = frame.numpy().reshape(f_shape[1], f_shape[2], f_shape[0])

                    output.append(frame)
            

        elif isinstance(clip[0], Image.Image):
            for frame in clip:
                output.append(np.array(frame))

        else:
            output = clip 

        output = np.array(output)

        #if output.max() > 1.0:
        #    output = output/255.

        return output


    def _to_tensor(self, clip):
        """
        torchvision converts PIL images and numpy arrays that are uint8 0 to 255 to float 0 to 1
        Converts numpy arrays that are float to float tensor
        """
            
        if isinstance(clip[0], torch.Tensor):
            return clip

        output = []
        for frame in clip:
            output.append(F.to_tensor(frame))
        
        return output





class ResizeClip(PreprocTransform):
    def __init__(self, *args, **kwargs):
        super(ResizeClip, self).__init__(*args, **kwargs)
        self.size_h, self.size_w = kwargs['resize_shape']
        
    def resize_bbox(self, xmin, ymin, xmax, ymax, img_shape, resize_shape):
        # Resize a bounding box within a frame relative to the amount that the frame was resized
    
        img_h = img_shape[0]
        img_w = img_shape[1]
    
        res_h = resize_shape[0]
        res_w = resize_shape[1]
    
        frac_h = res_h/float(img_h)
        frac_w = res_w/float(img_w)
    
        xmin_new = int(xmin * frac_w)
        xmax_new = int(xmax * frac_w)
    
        ymin_new = int(ymin * frac_h)
        ymax_new = int(ymax * frac_h)
    
        return xmin_new, ymin_new, xmax_new, ymax_new 


    def __call__(self, clip, bbox=[]):

        clip = self._to_numpy(clip)
        out_clip = []
        out_bbox = []
        for frame_ind in range(len(clip)):
            frame = clip[frame_ind]

            proc_frame = cv2.resize(frame, (self.size_w, self.size_h))
            out_clip.append(proc_frame)
            if bbox!=[]:
                temp_bbox = np.zeros(bbox[frame_ind].shape)-1 
                for class_ind in range(len(bbox[frame_ind])):
                    if np.array_equal(bbox[frame_ind,class_ind],-1*np.ones(4)): #only annotated objects
                        continue
                    xmin, ymin, xmax, ymax = bbox[frame_ind, class_ind]
                    proc_bbox = self.resize_bbox(xmin, ymin, xmax, ymax, frame.shape, (self.size_h, self.size_w))
                    temp_bbox[class_ind,:] = proc_bbox
                out_bbox.append(temp_bbox)

        out_clip = np.array(out_clip)

        assert(out_clip.shape[1:3] == (self.size_h, self.size_w)), 'Proc frame: {} Crop h,w: {},{}'.format(out_clip.shape,self.size_h,self.size_w)

        if bbox!=[]:
            return out_clip, np.array(out_bbox)
        else:
            return out_clip


class CropClip(PreprocTransform):
    def __init__(self, xmin, xmax, ymin, ymax, *args, **kwargs):
        super(CropClip, self).__init__(*args, **kwargs)
        self.crop_xmin = xmin
        self.crop_xmax = xmax
        self.crop_ymin = ymin
        self.crop_ymax = ymax

        self.crop_h, self.crop_w = kwargs['crop_shape']


    def _update_bbox(self, xmin, xmax, ymin, ymax):
        self.crop_xmin = xmin
        self.crop_xmax = xmax
        self.crop_ymin = ymin
        self.crop_ymax = ymax


    def crop_bbox(self, xmin, ymin, xmax, ymax, crop_xmin, crop_ymin, crop_xmax, crop_ymax):
        if (xmin >= crop_xmax) or (xmax <= crop_xmin) or (ymin >= crop_ymax) or (ymax <= crop_ymin):
            return -1, -1, -1, -1
    
        if ymax > crop_ymax:
            ymax_new = crop_ymax
        else:
            ymax_new = ymax
    
        if xmax > crop_xmax:
            xmax_new = crop_xmax
        else:
            xmax_new = xmax
        
        if ymin < crop_ymin:
            ymin_new = crop_ymin
        else:
            ymin_new = ymin 
    
        if xmin < crop_xmin:
            xmin_new = crop_xmin
        else:
            xmin_new = xmin 
    
        return xmin_new-crop_xmin, ymin_new-crop_ymin, xmax_new-crop_xmin, ymax_new-crop_ymin


        
    def __call__(self, clip, bbox=[]):
        out_clip = []
        out_bbox = []

        for frame_ind in range(len(clip)):
            frame = clip[frame_ind]
            proc_frame = np.array(frame[self.crop_ymin:self.crop_ymax, self.crop_xmin:self.crop_xmax]) 
            out_clip.append(proc_frame)

            assert(proc_frame.shape[:2] == (self.crop_h, self.crop_w)), 'Frame shape: {}, Proc frame: {} Crop h,w: {},{}'.format(frame.shape, proc_frame.shape,self.crop_h,self.crop_w)

            if bbox!=[]:
                temp_bbox = np.zeros(bbox[frame_ind].shape)-1 
                for class_ind in range(len(bbox)):
                    if np.array_equal(bbox[frame_ind,class_ind],-1*np.ones(4)): #only annotated objects
                        continue
                    xmin, ymin, xmax, ymax = bbox[frame_ind, class_ind]
                    proc_bbox = self.crop_bbox(xmin, ymin, xmax, ymax, self.crop_xmin, self.crop_ymin, self.crop_xmax, self.crop_ymax)
                    temp_bbox[class_ind,:] = proc_bbox
                out_bbox.append(temp_bbox)

        if bbox!=[]:
            return np.array(out_clip), np.array(out_bbox)
        else:
            return np.array(out_clip)


class RandomCropClip(PreprocTransform):
    def __init__(self, *args, **kwargs):
        super(RandomCropClip, self).__init__(*args, **kwargs)
        self.crop_h, self.crop_w = kwargs['crop_shape']

        self.crop_transform = CropClip(0, 0, self.crop_w, self.crop_h, **kwargs)

        self.xmin = None
        self.xmax = None
        self.ymin = None
        self.ymax = None


    def _update_random_sample(self, frame_h, frame_w):
        if frame_w == self.crop_w:
            self.xmin = 0
        else:
            self.xmin = np.random.randint(0, frame_w-self.crop_w)   

        self.xmax = self.xmin + self.crop_w

        if frame_h == self.crop_h:
            self.ymin = 0
        else:
            self.ymin = np.random.randint(0, frame_h-self.crop_h)
        
        self.ymax = self.ymin + self.crop_h

    def get_random_sample(self):
        return self.xmin, self.xmax, self.ymin, self.ymax
        
    def __call__(self, clip, bbox=[]):
        frame_shape = clip[0].shape
        self._update_random_sample(frame_shape[0], frame_shape[1])
        self.crop_transform._update_bbox(self.xmin, self.xmax, self.ymin, self.ymax) 
        proc_clip = self.crop_transform(clip, bbox)
        if isinstance(proc_clip, tuple):
            assert(proc_clip[0].shape[1:3] == (self.crop_h, self.crop_w)), 'Proc frame: {} Crop h,w: {},{}'.format(proc_clip[0].shape,self.crop_h,self.crop_w)
        else:
            assert(proc_clip.shape[1:3] == (self.crop_h, self.crop_w)), 'Proc frame: {} Crop h,w: {},{}'.format(proc_clip.shape,self.crop_h,self.crop_w)
        return proc_clip 

class CenterCropClip(PreprocTransform):
    def __init__(self, *args, **kwargs):
        super(CenterCropClip, self).__init__(*args, **kwargs)
        self.crop_h, self.crop_w = kwargs['crop_shape']

        self.crop_transform = CropClip(0, 0, self.crop_w, self.crop_h, **kwargs)

    def _calculate_center(self, frame_h, frame_w):
        xmin = int(frame_w/2 - self.crop_w/2)
        xmax = int(frame_w/2 + self.crop_w/2)
        ymin = int(frame_h/2 - self.crop_h/2)
        ymax = int(frame_h/2 + self.crop_h/2)
        return xmin, xmax, ymin, ymax
        
    def __call__(self, clip, bbox=[]):
        frame_shape = clip[0].shape
        xmin, xmax, ymin, ymax = self._calculate_center(frame_shape[0], frame_shape[1])
        self.crop_transform._update_bbox(xmin, xmax, ymin, ymax) 
        proc_clip =  self.crop_transform(clip, bbox)
        if isinstance(proc_clip, tuple):
            assert(proc_clip[0].shape[1:3] == (self.crop_h, self.crop_w)), 'Proc frame: {} Crop h,w: {},{}'.format(proc_clip[0].shape,self.crop_h,self.crop_w)
        else:
            assert(proc_clip.shape[1:3] == (self.crop_h, self.crop_w)), 'Proc frame: {} Crop h,w: {},{}'.format(proc_clip.shape,self.crop_h,self.crop_w)
        return proc_clip


class RandomFlipClip(PreprocTransform):
    """   
    Specify a flip direction:
    Horizontal, left right flip = 'h' (Default)
    Vertical, top bottom flip = 'v'
    """
    def __init__(self, direction='h', p=0.5, *args, **kwargs):
        super(RandomFlipClip, self).__init__(*args, **kwargs)
        self.direction = direction
        self.p = p
            
    def _random_flip(self):
        flip_prob = np.random.random()
        if flip_prob >= self.p:
            return 0
        else:
            return 1

    def _h_flip(self, bbox, frame_size):
        bbox_shape = bbox.shape
        output_bbox = np.zeros(bbox_shape)-1
        for bbox_ind in range(bbox_shape[0]):
            xmin, ymin, xmax, ymax = bbox[bbox_ind] 
            width = frame_size[1]
            xmax_new = width - xmin 
            xmin_new = width - xmax
            output_bbox[bbox_ind] = xmin_new, ymin, xmax_new, ymax
        return output_bbox 

    def _v_flip(self, bbox, frame_size):
        bbox_shape = bbox.shape
        output_bbox = np.zeros(bbox_shape)-1
        for bbox_ind in range(bbox_shape[0]):
            xmin, ymin, xmax, ymax = bbox[bbox_ind] 
            height = frame_size[0]
            ymax_new = height - ymin 
            ymin_new = height - ymax
            output_bbox[bbox_ind] = xmin, ymin_new, xmax, ymax_new
        return output_bbox 


    def _flip_data(self, clip, bbox=[]):
        output_bbox = []
        
        if self.direction == 'h':
            output_clip = [cv2.flip(np.array(frame), 1) for frame in clip]
            
            if bbox!=[]:
                output_bbox = [self._h_flip(frame, output_clip[0].shape) for frame in bbox] 

        elif self.direction == 'v':
            output_clip = [cv2.flip(np.array(frame), 0) for frame in clip]

            if bbox!=[]:
                output_bbox = [self._v_flip(frame, output_clip[0].shape) for frame in bbox]

        return output_clip, output_bbox 
        

    def __call__(self, clip, bbox=[]):
        input_shape = np.array(clip).shape
        flip = self._random_flip()
        out_clip = clip
        out_bbox = bbox
        if flip:
            out_clip, out_bbox = self._flip_data(clip, bbox)

        out_clip = np.array(out_clip)
        assert(input_shape == out_clip.shape), "Input shape {}, output shape {}".format(input_shape, out_clip.shape)

        if bbox!=[]:
            return out_clip, out_bbox
        else:
            return out_clip

class ToTensorClip(PreprocTransform):
    """
    Convert a list of PIL images or numpy arrays to a 5 dimensional pytorch tensor [batch, frame, channel, height, width]
    """
    def __init__(self, *args, **kwargs):
        super(ToTensorClip, self).__init__(*args, **kwargs)

        self.transform = torchvision.transforms.ToTensor()

    def __call__(self, clip, bbox=[]):
        
        if isinstance(clip[0], Image.Image):
            # a little round-about but it maintains consistency
            temp_clip = []
            for c in clip:
                temp_clip.append(np.array(c))
            clip = temp_clip 

        output_clip = torch.from_numpy(np.array(clip)).float() #Numpy array to Tensor

        if bbox!=[]:
            bbox = torch.from_numpy(np.array(bbox))
            return output_clip, bbox
        else:
            return output_clip
        

class RandomRotateClip(PreprocTransform):
    """
    Randomly rotate a clip from a fixed set of angles.
    The rotation is counterclockwise
    """
    def __init__(self,  angles=[0,90,180,270], *args, **kwargs):
        super(RandomRotateClip, self).__init__(*args, **kwargs)
        self.angles = angles

    ######
    # Code from: https://stackoverflow.com/questions/20924085/python-conversion-between-coordinates
    def _cart2pol(self, point):
        x,y = point
        rho = np.sqrt(x**2 + y**2)
        phi = np.arctan2(y, x)
        return(rho, phi)
    
    def _pol2cart(self, point):
        rho, phi = point
        x = rho * np.cos(phi)
        y = rho * np.sin(phi)
        return(x, y)
    #####

    def _update_angles(self, angles):
        self.angles=angles


    def _rotate_bbox(self, bboxes, frame_shape, angle):
        angle = np.deg2rad(angle)
        bboxes_shape = bboxes.shape
        output_bboxes = np.zeros(bboxes_shape)-1
        frame_h, frame_w = frame_shape[0], frame_shape[1] 
        half_h = frame_h/2. 
        half_w = frame_w/2. 

        for bbox_ind in range(bboxes_shape[0]):
            xmin, ymin, xmax, ymax = bboxes[bbox_ind]
            tl = (xmin-half_w, ymax-half_h)
            tr = (xmax-half_w, ymax-half_h)
            bl = (xmin-half_w, ymin-half_h)
            br = (xmax-half_w, ymin-half_h)

            tl = self._cart2pol(tl) 
            tr = self._cart2pol(tr)    
            bl = self._cart2pol(bl)
            br = self._cart2pol(br)

            tl = (tl[0], tl[1] - angle)
            tr = (tr[0], tr[1] - angle)
            bl = (bl[0], bl[1] - angle)
            br = (br[0], br[1] - angle)

            tl = self._pol2cart(tl) 
            tr = self._pol2cart(tr)    
            bl = self._pol2cart(bl)
            br = self._pol2cart(br)

            tl = (tl[0]+half_w, tl[1]+half_h)
            tr = (tr[0]+half_w, tr[1]+half_h)
            bl = (bl[0]+half_w, bl[1]+half_h)
            br = (br[0]+half_w, br[1]+half_h)

            xmin_new = int(np.clip(min(floor(tl[0]), floor(tr[0]), floor(bl[0]), floor(br[0])), 0, frame_w-1))
            xmax_new = int(np.clip(max(ceil(tl[0]), ceil(tr[0]), ceil(bl[0]), ceil(br[0])), 0, frame_w-1))
            ymin_new = int(np.clip(min(floor(tl[1]), floor(tr[1]), floor(bl[1]), floor(br[1])), 0, frame_h-1))
            ymax_new = int(np.clip(max(ceil(tl[1]), ceil(tr[1]), ceil(bl[1]), ceil(br[1])), 0, frame_h-1))

            output_bboxes[bbox_ind] = [xmin_new, ymin_new, xmax_new, ymax_new]

        return output_bboxes



    def __call__(self, clip, bbox=[]):
        angle = np.random.choice(self.angles)
        output_clip = []
        clip = self._to_numpy(clip)
        for frame in clip:
            output_clip.append(ndimage.rotate(frame, angle, reshape=False))

        if bbox!=[]:
            bbox = np.array(bbox)
            output_bboxes = np.zeros(bbox.shape)-1
            for bbox_ind in range(bbox.shape[0]):
                output_bboxes[bbox_ind] = self._rotate_bbox(bbox[bbox_ind], clip[0].shape, angle)

            return output_clip, output_bboxes 

        return output_clip



class SubtractMeanClip(PreprocTransform):
    def __init__(self, **kwargs):
        super(SubtractMeanClip, self).__init__(**kwargs)
#        self.clip_mean = torch.tensor(kwargs['clip_mean']).float()
        self.clip_mean = kwargs['clip_mean']
#        self.clip_mean      = []
#
#        for frame in self.clip_mean_args:
#            self.clip_mean.append(Image.fromarray(frame))

        
    def __call__(self, clip, bbox=[]):
        #clip = clip-self.clip_mean
        for clip_ind in range(len(clip)):
            clip[clip_ind] = clip[clip_ind] - self.clip_mean[clip_ind]

        
        if bbox!=[]:
            return clip, bbox

        else:
            return clip

class SubtractRGBMean(PreprocTransform):
    def __init__(self, **kwargs):
        super(SubtractRGBMean, self).__init__(**kwargs)
        self.rgb_mean = kwargs['subtract_mean']
    
    def __call__(self, clip, bbox=[]):

        clip = self._to_numpy(clip)
        out_clip = []
        out_bbox = []

        for frame_ind in range(len(clip)):
            frame = clip[frame_ind]

            proc_frame = frame - self.rgb_mean
            out_clip.append(proc_frame)

        if bbox != []:
            return out_clip, bbox
        else:
            return out_clip

class ApplyToPIL(PreprocTransform):
    """
    Apply standard pytorch transforms that require PIL images as input to their __call__ function, for example Resize

    NOTE: The __call__ function of this class converts the clip to a list of PIL images in the form of integers from 0-255. If the clips are floats (for example afer mean subtraction), then only call this transform before the float transform

    Bounding box coordinates are not guaranteed to be transformed properly!

    https://pytorch.org/docs/stable/_modules/torchvision/transforms/transforms.html
    """
    def __init__(self, **kwargs):
        """
        class_kwargs is a dictionary that contains the keyword arguments to be passed to the chosen pytorch transform class
        """
        super(ApplyToPIL, self).__init__( **kwargs)
        self.kwargs = kwargs
        self.class_kwargs = kwargs['class_kwargs']
        self.transform = kwargs['transform'](**self.class_kwargs)

    def __call__(self, clip, bbox=[]):
        if not isinstance(clip[0], Image.Image):
            clip = self._to_pil(clip)
        output_clip = []
        for frame in clip:
            output_clip.append(self.transform(frame))

        if bbox!=[]:
            return output_clip, bbox

        else:
            return output_clip


class ApplyToTensor(PreprocTransform):
    """
    Apply standard pytorch transforms that require pytorch Tensors as input to their __call__ function, for example Normalize 

    NOTE: The __call__ function of this class converts the clip to a pytorch float tensor. If other transforms require PIL inputs, call them prior tho this one
    Bounding box coordinates are not guaranteed to be transformed properly!

    https://pytorch.org/docs/stable/_modules/torchvision/transforms/transforms.html
    """
    def __init__(self, **kwargs):
        super(ApplyToTensor, self).__init__(**kwargs)
        self.kwargs = kwargs
        self.class_kwargs = kwargs['class_kwargs']
        self.transform = kwargs['transform'](**self.class_kwargs)

    def __call__(self, clip, bbox=[]):
        if not isinstance(clip, torch.Tensor):
            clip = self._to_tensor(clip)

        output_clip = []
        for frame in clip:
            output_clip.append(self.transform(frame))

        output_clip = torch.stack(output_clip)

        if bbox!=[]:
            return output_clip, bbox

        else:
            return output_clip

class ApplyOpenCV(PreprocTransform):
    """
    Apply opencv transforms that require numpy arrays as input to their __call__ function, for example Rotate 

    NOTE: The __call__ function of this class converts the clip to a Numpy array. If other transforms require PIL inputs, call them prior tho this one

    Bounding box coordinates are not guaranteed to be transformed properly!
    """
    def __init__(self, **kwargs):
        super(ApplyOpenCV, self).__init__(**kwargs)
        self.kwargs = kwargs
        self.class_kwargs = kwargs['class_kwargs']
        self.transform = kwargs['transform']

    def __call__(self, clip, bbox=[]):
        if not isinstance(clip, torch.Tensor):
            clip = self._to_numpy(clip)

        output_clip = []
        for frame in clip:
            output_clip.append(self.transform(frame, **self.class_kwargs))


        if bbox!=[]:
            return output_clip, bbox

        else:
            return output_clip




class TestPreproc(object):
    def __init__(self):
        self.resize = ResizeClip(resize_shape = [2,2])
        self.crop = CropClip(0,0,0,0, crop_shape=[2,2])
        self.rand_crop = RandomCropClip(crop_shape=[2,2])
        self.cent_crop = CenterCropClip(crop_shape=[2,2])
        self.rand_flip_h = RandomFlipClip(direction='h', p=1.0)
        self.rand_flip_v = RandomFlipClip(direction='v', p=1.0)
        self.rand_rot = RandomRotateClip(angles=[90])
        self.sub_mean = SubtractMeanClip(clip_mean=np.zeros(1))
        self.applypil = ApplyToPIL(transform=torchvision.transforms.ColorJitter, class_kwargs=dict(brightness=1))
        self.applypil2 = ApplyToPIL(transform=torchvision.transforms.FiveCrop, class_kwargs=dict(size=(64,64)))
        self.applytensor = ApplyToTensor(transform=torchvision.transforms.Normalize, class_kwargs=dict(mean=torch.tensor([0.,0.,0.]), std=torch.tensor([1.,1.,1.])))
        self.applycv = ApplyOpenCV(transform=cv2.threshold, class_kwargs=dict(thresh=100, maxval=100, type=cv2.THRESH_TRUNC))
        self.preproc = PreprocTransform()

    def resize_test(self):
        inp = np.array([[[.1,.2,.3,.4],[.1,.2,.3,.4],[.1,.2,.3,.4]]]).astype(float)
        inp2 = np.array([[[.1,.1,.1,.1],[.2,.2,.2,.2],[.3,.3,.3,.3]]]).astype(float)
        expected_out = np.array([[[.15,.35],[.15,.35]]]).astype(float)
        expected_out2 = np.array([[[.125,.125],[.275,.275]]]).astype(float)
        out = self.resize(inp)
        out2 = self.resize(inp2)
        assert (False not in np.isclose(out,expected_out)) and (False not in np.isclose(out2,expected_out2))
        
        bbox = np.array([[[0,0,3,3]]]).astype(float)
        _, bbox_out = self.resize(inp, bbox)
        exp_bbox = np.array([[[0,0,1,2]]])
        assert (False not in np.isclose(bbox_out, exp_bbox))

    def crop_test(self):
        inp = np.array([[[.1,.2,.3],[.4,.5,.6],[.7,.8,.9]]]).astype(float)
        self.crop._update_bbox(1, 3, 1, 3)

        exp_out = np.array([[[.5,.6],[.8,.9]]]).astype(float)
        out = self.crop(inp)
        assert (False not in np.isclose(out,exp_out))

    def cent_crop_test(self):
        inp = np.array([[[.1,.2,.3,.4],[.1,.2,.3,.4],[.1,.2,.3,.4],[.1,.2,.3,.4]]]).astype(float)
        exp_out = np.array([[[.2,.3],[.2,.3]]]).astype(float)
        out = self.cent_crop(inp)
        assert (False not in np.isclose(out, exp_out))

    def rand_crop_test(self):
        inp = np.array([[[.1,.2,.3,.4],[.3,.4,.5,.6],[.2,.3,.4,.5],[.1,.2,.3,.4]]]).astype(float)
        out = self.rand_crop(inp)
        coords = self.rand_crop.get_random_sample()
        exp_out = np.array(inp[:, coords[2]:coords[3], coords[0]:coords[1]]).astype(float)
        assert (False not in np.isclose(out, exp_out))

    def rand_flip_test(self):
        inp = np.array([[[.1,.2,.3],[.4,.5,.6],[.7,.8,.9]]]).astype(float)
        exp_outh = np.array([[[.3,.2,.1],[.6,.5,.4],[.9,.8,.7]]]).astype(float)
        exp_outv = np.array([[[.7,.8,.9],[.4,.5,.6],[.1,.2,.3]]]).astype(float)
        outh = self.rand_flip_h(inp)
        outv = self.rand_flip_v(inp)       
        assert (False not in np.isclose(outh,exp_outh)) and (False not in np.isclose(outv,exp_outv))


        inp2 = np.arange(36).reshape(6,6)
        bbox = np.array([[[0,0,2,2]]]).astype(float)
        exp_bboxh = np.array([[[4,0,6,2]]]).astype(float)
        exp_bboxv = np.array([[[0,4,2,6]]]).astype(float)
        _, bboxh = self.rand_flip_h([inp2], bbox)
        _, bboxv = self.rand_flip_v([inp2], bbox)       
         
        assert (False not in np.isclose(bboxh, exp_bboxh)) and (False not in np.isclose(bboxv, exp_bboxv))

    def rand_flip_vis(self):
        import matplotlib.pyplot as plt
        x = np.arange(112*112).reshape(112,112)
        x[:, 10] = 10000
        x[:, 50] = 5000
        x[10, :] = 5000
        x[50, :] = 10000
        plt.imshow(x); plt.show()
        h = self.rand_flip_h([x])
        plt.imshow(h[0]); plt.show()
        v = self.rand_flip_v([x])
        plt.imshow(v[0]); plt.show()


    def rand_rot_test(self):
        inp = np.array([[[.1,.2,.3],[.4,.5,.6],[.7,.8,.9]]]).astype(float)
        exp_out = np.array([[[.3,.6,.9],[.2,.5,.8],[.1,.4,.7]]]).astype(float)

        out = self.rand_rot(inp)


        self.rand_rot._update_angles([45])
        inp2 = np.arange(6*6).reshape(6,6)
        bbox = [[2,2,4,4]]
        exp_bbox = [1,1,5,5]
        out_bbox = self.rand_rot([inp2], np.array([bbox]))[1][0].tolist()
        assert (False not in np.isclose(out, exp_out)) and (False not in np.isclose(exp_bbox, out_bbox))

    def rand_rot_vis(self):
        import matplotlib.pyplot as plt
        self.rand_rot._update_angles([20])
        x = np.arange(112*112).reshape(112,112)
        #x = np.arange(6*6).reshape(6,6)
        #bbox = [51,51,61,61]
        bbox = [30,40,50,100]
        bbox = [30,40,50,110]
        #bbox = [2,2,4,4]
        plt1 = x[:]
        plt1[bbox[1]:bbox[3], bbox[0]] = 0
        plt1[bbox[1]:bbox[3], bbox[2]-1] = 0
        plt1[bbox[1], bbox[0]:bbox[2]] = 0
        plt1[bbox[3]-1, bbox[0]:bbox[2]] = 0
        plt.imshow(plt1); plt.show()
        out2 = self.rand_rot([x], np.array([[bbox]]))
        plt2 = out2[0][0]
        bbox = out2[1][0][0].astype(int)
        plt2[bbox[1]:bbox[3], bbox[0]] = 0
        plt2[bbox[1]:bbox[3], bbox[2]] = 0
        plt2[bbox[1], bbox[0]:bbox[2]] = 0
        plt2[bbox[3], bbox[0]:bbox[2]] = 0
        plt.imshow(plt2); plt.show()

    def applypil_test(self):
        inp = np.arange(112*112).reshape(112,112)
        inp = self.applypil._to_pil([inp, inp])
        inp = [inp[0].convert('RGB'), inp[1].convert('RGB')]
        out1 = self.applypil(inp)
        out = self.applypil2(out1)
        assert (len(out)==2) and (len(out[0])==5) and (out[0][0].size==(64,64)) and (isinstance(out[0][0], Image.Image))

    def applytensor_test(self):
        inp = np.arange(112*112*3).reshape(3,112,112).astype('float32')
        inp = torch.from_numpy(inp)
        out = self.applytensor([inp, inp])
        assert False not in np.array(inp==out)


    def applycv_test(self):
        inp = np.arange(112*112).reshape(112,112).astype('float32')
        out = self.applycv([inp])
        assert (out[0][1].min()==0.0) and (out[0][1].max()==100.0) 


    def to_numpy_test(self):
        inp_torch = [torch.zeros((3,112,112))]
        inp_pil = [Image.fromarray(np.zeros((112,112,3)).astype('uint8'))]
        out_torch = self.preproc._to_numpy(inp_torch)
        out_pil = self.preproc._to_numpy(inp_pil)

        assert (False not in np.array(out_pil==out_torch))


    def to_tensor_test(self):
        inp_np_f = np.zeros((1,112,112,3)).astype('float')+201
        inp_np = np.zeros((1,112,112,3)).astype('uint8')+1
        inp_pil = [Image.fromarray(inp_np[0], mode='RGB')]
        out_np_f = self.preproc._to_tensor(inp_np_f)
        out_np = self.preproc._to_tensor(inp_np)
        out_pil = self.preproc._to_tensor(inp_pil)
        assert (False not in np.array(out_np[0]==out_pil[0])) and isinstance(out_np_f[0], torch.DoubleTensor)


    def to_pil_test(self):
        inp_np = [np.zeros((112,112,3)).astype('int32')]
        inp_torch = [torch.zeros((3,112,112))]
        out_np = self.preproc._to_pil(inp_np)
        out_torch = self.preproc._to_pil(inp_torch)

        assert (False not in np.array(np.array(out_np[0])==np.array(out_torch[0])))


    def run_tests(self):
        self.resize_test()
        self.crop_test()
        self.cent_crop_test()
        self.rand_crop_test()
        self.rand_flip_test()
        self.rand_rot_test()
        self.applypil_test()
        self.applytensor_test()
        self.applycv_test()
        self.to_tensor_test()
        self.to_pil_test()
        self.to_numpy_test()
        print("Tests passed")
        #self.rand_flip_vis()
        #self.rand_rot_vis()
        



if __name__=='__main__':
    test = TestPreproc()
    test.run_tests()


