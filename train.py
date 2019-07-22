import torch
import utils.dataset as ds
from myargs import args
from tqdm import tqdm
import os
import utils.eval as val
import utils.networks as networktools
import segmentation_models_pytorch as smp
import models.losses as losses
from models import optimizers

os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu_ids


def train():

    args.val_save_pth = 'data/val/out2'

    ' model setup '
    def activation(x):
        x
    model = eval('smp.'+args.model_name)(
        args.arch_encoder,
        encoder_weights='imagenet',
        classes=args.num_classes,
        activation=activation,
    )
    optimizer = optimizers.optimfn(args.optim, model)

    model, optimizer, start_epoch = networktools.continue_train(model, optimizer,
                                                                args.train_model_pth, args.continue_train)
    ' losses '
    lossfn = losses.lossfn(args.loss).cuda()
    #lossfn = losses.lossfn('xent').cuda()
    lossfn2 = losses.lossfn('xent').cuda()
    ' datasets '
    validation_params = {
        'ph': args.tile_h,  # patch height (y)
        'pw': args.tile_w,  # patch width (x)
        'sh': args.tile_stride_h,     # slide step (dy)
        'sw': args.tile_stride_w,     # slide step (dx)
    }
    iterator_train = ds.GenerateIterator(args.train_image_pth)
    iterator_val = ds.Dataset_wsis(args.raw_val_pth, validation_params, bs=1)
    iterator_val1 = ds.Dataset_wsiswgt(args.raw_val1_pth, validation_params)

    cuda = torch.cuda.is_available()
    if cuda:
        model = model.cuda()
        lossfn = lossfn.cuda()

    ' current run train parameters '
    print(args)

    for epoch in range(start_epoch, 1+args.num_epoch):
        sum_loss_cls = 0
        progress_bar = tqdm(iterator_train, disable=False)

        for batch_it, (image, label, mask) in enumerate(progress_bar):
            if cuda:
                image = image.cuda()
                label = label.cuda()
                mask = mask.cuda()

            # pass images through the network (cls)
            pred_src = model(image)

            loss_cls = lossfn(pred_src, label) #+ lossfn2(pred_src, label).mean()

            sum_loss_cls = sum_loss_cls + loss_cls.item()

            optimizer.zero_grad()
            loss_cls.backward()
            optimizer.step()

            progress_bar.set_description('ep. {}, cls loss: {:.3f}'.format(epoch, sum_loss_cls/(batch_it+args.epsilon)))

        'zoom in stage'
        if 0 and epoch % args.save_models == 0:
            model.eval()
            with torch.no_grad():
                val.gen_heatmap(model, iterator_val1, epoch)
            model.train()

        ' test model accuracy '
        if epoch >= 1 and epoch % args.save_models == 0:
            model.eval()
            with torch.no_grad():
                val.predict_wsis(model, iterator_val, epoch)
            model.train()

        if 0 and args.save_models > 0 and epoch % args.save_models == 0:
            state = {
                'epoch': epoch,
                'state_dict': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'config': args
            }
            torch.save(state, '{}/model_{}_{}.pt'.format(args.model_save_pth, args.arch_encoder, epoch))


if __name__ == "__main__":
    train()