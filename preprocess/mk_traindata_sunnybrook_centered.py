'''
extract gt patches centered on patch
not random sliding windows
'''
import cv2
import openslide
import os
import numpy as np
from myargs import args
import glob
from utils.read_xml_sunnybrook import getGT
import utils.filesystem as ufs
from tqdm import tqdm
from PIL import Image
from sklearn.cluster import KMeans
import gc


def nextpow2(x):
    x = int(x)
    return 1 << (x-1).bit_length()


def ispow2(x):
    x = int(x)
    return x > 0 and (x & (x - 1))


args.raw_train_pth = 'data/sunnybrook/WSI'

ufs.make_folder('../' + args.train_image_pth, True)
wsipaths = glob.glob('../{}/*.svs'.format(args.raw_train_pth))

' check if metadata gt.npy already exists to append to it '
metadata_pth = '../{}/gt.npy'.format(args.train_image_pth)
metadata = ufs.fetch_metadata(metadata_pth)

pwhs = {
    np.maximum(args.tile_w, args.tile_h): 0
}

wsipaths = sorted(wsipaths)
patch_id = 0

for wsipath in tqdm(wsipaths):

    'read scan and get metadata'
    scan = openslide.OpenSlide(wsipath)
    filename = os.path.basename(wsipath)
    metadata[filename] = {}

    'get actual mask, i.e. the ground truth'
    xmlpath = '../{}/{}.xml'.format(args.raw_train_pth, filename.split('.svs')[0])
    gt = getGT(xmlpath, scan, level=args.scan_level)

    n_labels, labels, stats, centers = cv2.connectedComponentsWithStats((gt > 0).astype(np.uint8))
    centers = centers.astype(np.int)
    '''
    stats
    [left, top, width, height, area]
    '''

    for tile_id in range(1, n_labels):

        cx, cy = centers[tile_id, :]
        l, u = stats[tile_id, [0, 1]]
        w, h = stats[tile_id, [2, 3]]

        pwh = nextpow2(np.maximum(w, h))  # patch width/height

        if pwh <= np.maximum(args.tile_w, args.tile_h):

            pwh = np.maximum(pwh, int(args.tile_w/4))
            pwh = args.tile_w
            dx = dy = pwh//2

            if pwh not in pwhs:
                pwhs[pwh] = 0

            up, down = np.maximum(cy-dy, 1), np.minimum(cy+dy, gt.shape[0])
            left, right = np.maximum(cx-dx, 1), np.minimum(cx+dx, gt.shape[1])

            if up == 1:
                down = up + pwh
            if down == gt.shape[0]:
                up = down - pwh
            if left == 1:
                right = left + pwh
            if right == gt.shape[1]:
                left = right - pwh

            'patch paths'
            tilepth_w = '{}/w_{}_{}.png'.format(args.train_image_pth, filename, patch_id)
            tilepth_g = '{}/g_{}_{}.png'.format(args.train_image_pth, filename, patch_id)
            tilepth_m = '{}/m_{}_{}.png'.format(args.train_image_pth, filename, patch_id)

            ' save metadata '
            metadata[filename][patch_id] = {
                'wsi': tilepth_w,
                'label': tilepth_g,
                'mask': tilepth_m,
            }

            ' save images '
            gt_patch = gt[up:down, left:right]
            gt_patch = Image.fromarray(gt_patch.astype(np.uint8))
            gt_patch.save('../' + tilepth_g)

            wsi_patch = scan.read_region((left * (4 ** args.scan_level), up * (4 ** args.scan_level)),
                                         args.scan_level,
                                         (pwh, pwh)).convert('RGB')
            wsi_patch.save('../' + tilepth_w)

            msk_patch = np.zeros(gt_patch.size[::-1], dtype=np.uint8)
            msk_patch = Image.fromarray(msk_patch)
            msk_patch.save('../' + tilepth_m)

            patch_id = patch_id + 1
            pwhs[pwh] += 1

        else:

            label_patch = labels[u:u+h, l:l+w] == tile_id
            label_patch = Image.fromarray((255*label_patch).astype(np.uint8))
            label_patch = label_patch.resize((label_patch.size[0]//16, label_patch.size[1]//16))
            label_patch = np.asarray(label_patch)
            coords = np.transpose(np.where(label_patch))[:, ::-1]  # (x,y) pairs

            num_clusters = np.ceil(1+np.sqrt((w*h)/(args.tile_w*args.tile_h))).astype(np.int)
            kmeans = KMeans(n_clusters=num_clusters, random_state=0)
            cnt_pts = kmeans.fit(coords).cluster_centers_  # (x,y) centers
            cnt_pts = (16 * cnt_pts).astype(np.int)

            for _cx, _cy in cnt_pts:
                _cx = _cx + l
                _cy = _cy + u
                dx, dy = int(args.tile_w/2), int(args.tile_h/2)
                pwh = np.maximum(args.tile_w, args.tile_h)

                up, down = np.maximum(_cy - dy, 1), np.minimum(_cy + dy, gt.shape[0])
                left, right = np.maximum(_cx - dx, 1), np.minimum(_cx + dx, gt.shape[1])

                if up == 1:
                    down = up + pwh
                if down == gt.shape[0]:
                    up = down - pwh
                if left == 1:
                    right = left + pwh
                if right == gt.shape[1]:
                    left = right - pwh

                if up >= down or left >= right:
                    continue

                'patch paths'
                tilepth_w = '{}/w_{}_{}.png'.format(args.train_image_pth, filename, patch_id)
                tilepth_g = '{}/g_{}_{}.png'.format(args.train_image_pth, filename, patch_id)
                tilepth_m = '{}/m_{}_{}.png'.format(args.train_image_pth, filename, patch_id)

                ' save metadata '
                metadata[filename][patch_id] = {
                    'wsi': tilepth_w,
                    'label': tilepth_g,
                    'mask': tilepth_m,
                }

                ' save images '
                gt_patch = gt[up:down, left:right]
                gt_patch = Image.fromarray(gt_patch.astype(np.uint8))
                gt_patch.save('../' + tilepth_g)

                wsi_patch = scan.read_region((left * (4 ** args.scan_level), up * (4 ** args.scan_level)),
                                             args.scan_level,
                                             (pwh, pwh)).convert('RGB')
                wsi_patch.save('../' + tilepth_w)

                msk_patch = np.zeros(gt_patch.size[::-1], dtype=np.uint8)
                msk_patch = Image.fromarray(msk_patch)
                msk_patch.save('../' + tilepth_m)

                patch_id = patch_id + 1

                pwhs[pwh] += 1

    del gt


np.save(metadata_pth, metadata)

print(pwhs)
