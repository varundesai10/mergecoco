import imgaug as ia
from imgaug import augmenters as iaa
import json
import os
import numpy as np
import matplotlib.pyplot as plt
import imageio
from imgaug.augmentables.polys import Polygon, PolygonsOnImage
from imgaug.augmentables.bbs import BoundingBoxesOnImage
from imgaug.augmentables.bbs import BoundingBox
import sys
'''
Usage: python3 augmentdata.py <coco-json-name-input> <coco-json-name-output> <image-dir>
'''


def getBoundingBox(segmentation):
	x_min, x_max, y_min, y_max = None, None, None, None
	if(len(segmentation) == 0):
		return None
	for seg in segmentation:
		it = iter(seg)
		for x in it:
			y = next(it)
			if(x_min == None):
				x_min = x
			if(y_min == None):
				y_min = y
			if(x_max == None):
				x_max = x
			if(y_max == None):
				y_max = y

			if(y >= y_max):
				y_max = y
			elif(y <= y_min):
				y_min = y
			if(x >= x_max):
				x_max = x
			elif(x <= x_min):
				x_min = x
	width = x_max - x_min
	height = y_max - y_min

	return [int(x_min), int(y_min), int(width), int(height)]
def convertBboxStyle(bbox, convert_to = "imaug"):
	bbox2 = []
	if convert_to == "imaug":
		bbox2 = [bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]]
	else:
		bbox2 = [int(bbox[0]), int(bbox[1]), int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])]
	return bbox2

def AugmentData(d, input_dir, augmentations_dict, new_image_id, new_ann_id):
	TOTAL_IMAGES = len(d['images'])
	TOTAL_AUG = len(augmentations_dict.items())
	CURRENT_AUG_ITER = 1
	print('Applying a total of {} augmentations to a total of {} images'.format(TOTAL_AUG, TOTAL_IMAGES))
	for aug in augmentations_dict:
		prefix = augmentations_dict[aug]
		print('APPLYING AUGMENTATION {}. PREFIX = {}'.format(CURRENT_AUG_ITER, prefix))
		CURRENT_AUG_ITER += 1
		for CURRENT_IMAGE_ITER in range(TOTAL_IMAGES):
			print('Working on Image {}'.format(CURRENT_IMAGE_ITER+1))
			image_name = (d['images'][CURRENT_IMAGE_ITER]['file_name'])
			image_id = d['images'][CURRENT_IMAGE_ITER]['id']
			width = d['images'][CURRENT_IMAGE_ITER]['width']
			height = d['images'][CURRENT_IMAGE_ITER]['height']
			image = imageio.imread(os.path.join(input_dir, image_name))
			annotations = []
			for c in d['annotations']:
				if c['image_id']==image_id:
					annotations.append(c)
			segments = {i:[] for i in range(len(annotations))}
			categories = {}
			ids = {}
			bboxes = {}
			areas = {}
			for i in range(0, len(annotations)):
				for j in range(0, len(annotations[i]['segmentation'])):
					current_seg = []
					for k in range(0, len(annotations[i]['segmentation'][j]), 2):
						[x, y] = [annotations[i]['segmentation'][j][k], annotations[i]['segmentation'][j][k+1]]
						current_seg = current_seg + [[x, y]]
					segments[i] = segments[i] + [current_seg]
				categories[i] = annotations[i]['category_id']
				ids[i] = annotations[i]['id']
				bboxes[i] = convertBboxStyle(annotations[i]['bbox'])
				areas[i] = annotations[i]['area']
			num_annotations = len(annotations)
			POLYGONS = []

			for i in segments:
				for L in segments[i]:
					POLYGONS.append(Polygon(L))

			psoi = PolygonsOnImage(POLYGONS, shape=image.shape)
			bbsoi = BoundingBoxesOnImage(
				[BoundingBox(x1 = bboxes[i][0], y1= bboxes[i][1], x2 = bboxes[i][2], y2=bboxes[i][3]) for i in bboxes],
				shape=image.shape
			)

			image_aug, psoi_aug = aug(image=image, polygons=psoi)
			_, bbsoi_aug = aug(image=image, bounding_boxes = bbsoi)
			bboxes_converted = bbsoi_aug.items #List of bounding boxes

			#is there a need to do this?
			#not really sure. May remove this later.
			polygons_converted = [psoi_aug.polygons[i].exterior for i in range(len(psoi_aug.polygons))]
			
			#Generating coco_entry for the same.
			image_data = {
				"id":new_image_id,
				"width": width,
				"height": height,
				"file_name": '{}{}'.format(prefix,image_name),
				"license": 0
			}

			annotations_data = []
			polygon_index = 0
			for i in range(num_annotations):
				#to retreive: segments, bboxes
				num_segments = len(segments[i])
				SEGMENTATION = []
				AREA = 0
				for j in range(num_segments):
					#p = polygons_converted[polygon_index + j]
					current_polygon = psoi_aug.polygons[polygon_index +j]
					if(current_polygon.is_valid):
						if(current_polygon.is_fully_within_image(image_aug)):
							polygons_list = [current_polygon]
							print("WITHIN")
						else:
							try:
								print("NOTWITHIN")
								polygons_list = current_polygon.clip_out_of_image(image_aug) #now this is a list of polyogns that the current polygon may have split into.
							except AssertionError:
								print("Assertion Error occured. Ignoring. Can't guarantee that final dataset will be accurate.")
								polygons_list = [current_polygon]
						#add this to the SEGMENTATION
						s = []
						for P in polygons_list:
							AREA += P.area
							p = P.exterior
							for k in range(len(p)):
								[x,y] = p[k]
								s.append(int(x))
								s.append(int(y))

							s.append(s[0])
							s.append(s[1])
							SEGMENTATION = SEGMENTATION + [s]
					else:
						print("Polygon Invalid, skiiping: ", current_polygon)
				polygon_index = polygon_index + j + 1
				bboxes_converted[i].clip_out_of_image_(image_aug)
				#bbox = [bboxes_converted[i].x1_int, bboxes_converted[i].y1_int, int(bboxes_converted[i].width), int(bboxes_converted[i].height)]
				#bbox = convertBboxStyle(bbox, "s")
				bbox = getBoundingBox(SEGMENTATION)
				if(len(SEGMENTATION) > 0):
					A = {
						"id":new_ann_id,
						"image_id": new_image_id,
						"category_id": categories[i],
						"segmentation": (SEGMENTATION),
						"area": int(AREA),
						"bbox": (bbox),
						"iscrowd": 0
					}
					annotations_data.append(A)
					new_ann_id += 1
			new_image_id += 1
			d['images'].append(image_data)
			d['annotations'] += annotations_data
			imageio.imwrite(os.path.join(input_dir, '{}{}'.format(prefix, image_name)), image_aug)
	return d

def main():
	json_file_name_in = sys.argv[1]
	json_file_name_out = sys.argv[2]
	input_dir = sys.argv[3]

	with open(json_file_name_in) as f:
		d = json.load(f)


	aug1 = iaa.Affine(rotate=(20,70))
	aug2 = iaa.Rot90(1)
	aug3 = iaa.Fliplr()
	aug4 = iaa.Flipud()

	aug_dict = {aug1:'rot20_70', aug2:'rot90_', aug3:'flipx_', aug4:'flipy_'}
	current_ann_id = -1
	current_img_id = -1
	for a in d['images']:
		if(a['id']>=current_img_id):
			current_img_id = a['id'] + 1
	for a in d['annotations']:
		if(a['id']>=current_ann_id):
			current_ann_id = a['id'] + 1
	print(current_img_id, current_ann_id)

	#applying augmentation:
	d = AugmentData(d, input_dir, aug_dict, current_img_id, current_ann_id)
	with open(json_file_name_out, 'w') as f:
		json.dump(d, f)

	print('File Saved. Job done.')
if __name__ == '__main__':
	main()