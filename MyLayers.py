from __future__ import print_function

import os

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# supress annoying TF messages at the beginning
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf

from tensorflow.keras.layers import Layer
from tensorflow.keras import backend as K
import numpy as np

from MyFunctions import nines, heconstant, mynormal, myuniform, activate, mask, mask_rs, flip, binary, mask_flip, ternary, quaternary, tf_count

minval = 0.01
maxval = 0.1


class MaskedConv2D(Layer):
    def __init__(self, ksize, filters, activation, seed, initializer, stride, masktype, trainweights, trainmask, p1, abg, **kwargs):
        self.filters = filters

        # used for weight initialization
        self.seed = seed
        self.stride = 1

        self.p1 = p1

        self.alpha, self.beta, self.gamma = abg

        if stride is not None:
            self.stride = stride

        self.initializer = initializer

        if masktype == "flip":
            self.masktype = flip

        if masktype == "mask":
            self.masktype = mask

        if masktype == "mask_rs":
            self.masktype = mask_rs

        if masktype == "mask_flip":
            self.masktype = mask_flip

        self.trainW = trainweights
        self.trainM = trainmask

        # convolutional kernel size
        self.kernelsize = ksize

        # used for activation
        self.activation = activation

        super(MaskedConv2D, self).__init__(**kwargs)

    def build(self, input_shape):
        if self.initializer == 'normal':
            ki = tf.compat.v1.keras.initializers.RandomNormal(mean=0., stddev=0.05, seed=self.seed)

        if self.initializer == 'glorot':
            ki = tf.compat.v1.keras.initializers.glorot_normal(self.seed)

        if self.initializer == 'he':
            ki = tf.compat.v1.keras.initializers.he_normal(self.seed)

        if self.initializer == "heconstant":
            ki = heconstant(self.p1, self.seed)

        if self.initializer == "mynormal":
            ki = mynormal

        if self.initializer == "myuniform":
            ki = myuniform

        if self.initializer == "binary":
            ki = binary(self.p1, self.seed)

        if self.initializer == "ternary":
            ki = ternary

        if self.initializer == "quaternary":
            ki = quaternary

        if self.initializer == "ones":
            ki = tf.compat.v1.keras.initializers.ones()

        kshape = list(self.kernelsize) + [input_shape.as_list()[-1], self.filters]
        self.kernel = self.add_weight(name='kernel', shape=kshape, initializer=ki, trainable=self.trainW)

        si = tf.compat.v1.keras.initializers.RandomUniform(minval=minval, maxval=maxval, seed=self.seed)
        self.score = self.add_weight(name='score', shape=kshape, initializer=si, trainable=self.trainM)

        if self.alpha != 0:
            self.add_loss(self.alpha * (self.beta + self.gamma * tf.reduce_mean(self.masktype(self.score))))

        # self.add_loss(tf.math.abs(tf.reduce_mean(self.masktype(self.score)) + beta))

        super(MaskedConv2D, self).build(input_shape)  # Be sure to call this at the end

    def call(self, x):
        """
        THis is the layer's logic
        :param x: input
        :return: output
        """

        act = K.conv2d(x, self.kernel * self.masktype(self.score), strides=(self.stride, self.stride), padding='same')
        act = activate(act, self.activation)

        return act

    # needed for keras to calculate the outputshape of an operation
    def compute_output_shape(self, input_shape):
        return (input_shape.as_list()[1], self.output_dim)

    # called for a layer's weights, ignored (apparently) if called from the Model
    def get_weights(self):
        return K.eval(self.kernel)

    def get_pruneamount(self):
        weights_mask = K.eval(self.masktype(self.score))
        nz = np.count_nonzero(weights_mask)
        total = weights_mask.size
        return nz, total, nz / total

    def get_score(self):
        return K.eval(self.score)

    def get_mask(self):
        return K.eval(self.masktype(self.score))

    def get_kernel(self):
        return K.eval(self.kernel)

    def get_seed(self):
        return self.seed

    def set_weights(self, weights):
        super(MaskedConv2D, self).set_weights(weights)


class MaskedDense(Layer):

    def __init__(self, output_dim, activation, seed, initializer, masktype, trainweights, trainmask, p1, abg, **kwargs):
        self.output_dim = output_dim
        self.seed = seed
        self.p1 = p1
        self.alpha = abg
        self.initializer = initializer
        self.trainW = trainweights
        self.trainM = trainmask
        self.activation = activation

        if masktype == "flip":
            self.masktype = flip

        if masktype == "mask":
            self.masktype = mask

        if masktype == "mask_rs":
            self.masktype = mask_rs

        if masktype == "mask_flip":
            self.masktype = mask_flip

        super(MaskedDense, self).__init__(**kwargs)

    def build(self, input_shape):

        ki = self.kernel_initializer()
        kshape = (input_shape.as_list()[1], self.output_dim)

        self.kernel = self.add_weight(name='kernel', shape=kshape, initializer=ki, trainable=self.trainW)

        si = tf.compat.v1.keras.initializers.RandomUniform(minval=minval, maxval=maxval, seed=self.seed)
        self.score = self.add_weight(name='score', shape=kshape, initializer=si, trainable=self.trainM)

        if self.alpha != 0:
            minfunction = None
            reduce_mean = tf.reduce_mean(self.masktype(self.score))
            reduce_sum = tf.reduce_sum(self.masktype(self.score))
            count_nonzero_absolute = tf.math.count_nonzero(self.masktype(self.score), dtype=tf.dtypes.float32)
            count_nonzero_relative = tf.math.count_nonzero(self.masktype(self.score), dtype=tf.dtypes.float32) / tf.compat.v1.size(self.score, out_type=tf.dtypes.float32)
            #
            #     # count_nines = a - self.nins
            #
            #     '''
            #     minfunction = tf.reduce_sum(self.masktype(self.score))  # this function  is bad, the network reduces everything to 0
            #
            #     this particular function does no work at all in the following setup:
            #     TF version:         1.14.0
            #     TF.keras version:   2.2.4-tf
            #     '''
            #
            minfunction = count_nonzero_absolute
            # minfunction = count_nonzero_relative
            minfunction = reduce_mean

            # self.add_loss(self.alpha * (self.beta + self.gamma * minfunction))
            self.add_loss(self.alpha * minfunction)
            # self.add_loss(tf.math.square(minfunction))
            # self.add_loss(tf.math.square(self.alpha * (self.beta + self.gamma * minfunction)))
            # self.add_loss(self.alpha * (self.beta + self.gamma * minfunction))
            # self.add_loss(minfunction)

        super(MaskedDense, self).build(input_shape)  # Be sure to call this at the end

    def call(self, x):
        act = K.dot(x, self.kernel * self.masktype(self.score))
        act = activate(act, self.activation)
        return act

    def kernel_initializer(self):
        if self.initializer == 'normal':
            ki = tf.compat.v1.keras.initializers.RandomNormal(mean=0.1, stddev=0.05, seed=self.seed)

        if self.initializer == 'glorot':
            ki = tf.compat.v1.keras.initializers.glorot_normal(self.seed)

        if self.initializer == 'he':
            ki = tf.compat.v1.keras.initializers.he_normal(self.seed)

        if self.initializer == "heconstant":
            ki = heconstant(self.p1, self.seed)

        if self.initializer == "mynormal":
            ki = mynormal

        if self.initializer == "myuniform":
            ki = myuniform

        if self.initializer == "binary":
            ki = binary(self.p1, self.seed)

        if self.initializer == "ternary":
            ki = ternary

        if self.initializer == "quaternary":
            ki = quaternary

        return ki

    def compute_output_shape(self, input_shape):
        return input_shape.as_list()[1], self.output_dim

    def get_weights(self):
        return K.eval(self.kernel)

    def get_pruneamount(self):
        weights_mask = K.eval(self.masktype(self.score))
        nz = np.count_nonzero(weights_mask)
        total = weights_mask.size
        return nz, total, nz / total

    def get_score(self):
        return K.eval(self.score)

    def get_mask(self):
        return K.eval(self.masktype(self.score))

    def get_kernel(self):
        return K.eval(self.kernel)

    def get_seed(self):
        return self.seed

    def set_weights(self, weights):
        super(MaskedDense, self).set_weights(weights)
