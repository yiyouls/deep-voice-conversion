# -*- coding: utf-8 -*-
#/usr/bin/python2

from __future__ import print_function

from hparam import logdir_path
from tqdm import tqdm

import tensorflow as tf
from models import Model
import convert, eval2
from data_load import get_batch
import argparse
from hparam import Hparam


def train(logdir1, logdir2, queue=True):
    hp = Hparam.get_global_hparam()

    model = Model(mode="train2", batch_size=hp.train2.batch_size, hp=hp, queue=queue)

    # Loss
    loss_op = model.loss_net2()

    # Training Scheme
    epoch, gs = Model.get_epoch_and_global_step(logdir2)
    global_step = tf.Variable(gs, name='global_step', trainable=False)

    optimizer = tf.train.AdamOptimizer(learning_rate=hp.train2.lr)
    with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
        var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'net/net2')

        # Gradient clipping to prevent loss explosion
        gvs = optimizer.compute_gradients(loss_op, var_list=var_list)
        clipped_gvs = [(tf.clip_by_value(grad, hp.train2.clip_value_min, hp.train2.clip_value_max), var) for grad, var in gvs]
        train_op = optimizer.apply_gradients(clipped_gvs, global_step=global_step)

    # Summary
    summ_op = summaries(loss_op)

    session_conf = tf.ConfigProto(
        gpu_options=tf.GPUOptions(
            allow_growth=True,
            per_process_gpu_memory_fraction=0.6,
        ),
    )
    # Training
    with tf.Session(config=session_conf) as sess:
        # Load trained model
        sess.run(tf.global_variables_initializer())
        model.load(sess, mode='train2', logdir=logdir1, logdir2=logdir2)

        writer = tf.summary.FileWriter(logdir2)
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(coord=coord)

        for epoch in range(epoch + 1, hp.train2.num_epochs + 1):
            for _ in tqdm(range(model.num_batch), total=model.num_batch, ncols=70, leave=False, unit='b'):
                if queue:
                    sess.run(train_op)
                else:
                    mfcc, spec, mel = get_batch(model.mode, model.batch_size)
                    sess.run(train_op, feed_dict={model.x_mfcc: mfcc, model.y_spec: spec, model.y_mel: mel})

            # Write checkpoint files at every epoch
            summ, gs = sess.run([summ_op, global_step])

            if epoch % hp.train2.save_per_epoch == 0:
                tf.train.Saver().save(sess, '{}/epoch_{}_step_{}'.format(logdir2, epoch, gs))

                # Eval at every n epochs
                with tf.Graph().as_default():
                    eval2.eval(logdir2, queue=False, writer=writer)

                # Convert at every n epochs
                with tf.Graph().as_default():
                    convert.convert(logdir2, queue=False, writer=writer)

            writer.add_summary(summ, global_step=gs)

        writer.close()
        coord.request_stop()
        coord.join(threads)


def summaries(loss):
    # for v in tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'net/net2'):
    #     tf.summary.histogram(v.name, v)
    tf.summary.scalar('net2/train/loss', loss)
    return tf.summary.merge_all()


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('case1', type=str, help='experiment case name of train1')
    parser.add_argument('case2', type=str, help='experiment case name of train2')
    arguments = parser.parse_args()
    return arguments

if __name__ == '__main__':
    args = get_arguments()
    case1, case2 = args.case1, args.case2
    logdir1 = '{}/{}/train1'.format(logdir_path, case1)
    logdir2 = '{}/{}/train2'.format(logdir_path, case2)
    Hparam(case2).set_as_global_hparam()

    train(logdir1=logdir1, logdir2=logdir2)

    print("Done")