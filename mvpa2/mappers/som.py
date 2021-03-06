# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Self-organizing map (SOM) mapper."""

__docformat__ = 'restructuredtext'


import numpy as np
from mvpa2.mappers.base import Mapper, accepts_dataset_as_samples

if __debug__:
    from mvpa2.base import debug

class SimpleSOMMapper(Mapper):
    """Mapper using a self-organizing map (SOM) for dimensionality reduction.

    This mapper provides a simple, but pretty fast implementation of a
    self-organizing map using an unsupervised training algorithm. It performs a
    ND -> 2D mapping, which can for, example, be used for visualization of
    high-dimensional data.

    This SOM implementation uses squared Euclidean distance to determine
    the best matching Kohonen unit and a Gaussian neighborhood influence
    kernel.
    """
    def __init__(self, kshape, niter, learning_rate=0.005,
                 iradius=None):
        """
        Parameters
        ----------
        kshape : (int, int)
          Shape of the internal Kohonen layer. Currently, only 2D Kohonen
          layers are supported, although the length of an axis might be set
          to 1.
        niter : int
          Number of iteration during network training.
        learning_rate : float
          Initial learning rate, which will continuously decreased during
          network training.
        iradius : float or None
          Initial radius of the Gaussian neighborhood kernel radius, which
          will continuously decreased during network training. If `None`
          (default) the radius is set equal to the longest edge of the
          Kohonen layer.
        """
        # init base class
        Mapper.__init__(self)

        self.kshape = np.array(kshape, dtype='int')

        if iradius is None:
            self.radius = self.kshape.max()
        else:
            self.radius = iradius

        # learning rate
        self.lrate = learning_rate

        # number of training iterations
        self.niter = niter

        # precompute whatever can be done
        # scalar for decay of learning rate and radius across all iterations
        self.iter_scale = self.niter / np.log(self.radius)

        # the internal kohonen layer
        self._K = None


    @accepts_dataset_as_samples
    def _train(self, samples):
        """Perform network training.

        Parameter
        ---------
        samples : array-like
          Used for unsupervised training of the SOM.
        """
        # XXX initialize with clever default, e.g. plain of first two PCA
        # components
        self._K = np.random.standard_normal(tuple(self.kshape) + (samples.shape[1],))

        # units weight vector deltas for batch training
        # (height x width x #features)
        unit_deltas = np.zeros(self._K.shape, dtype='float')

        # precompute distance kernel between elements in the Kohonen layer
        # that will remain constant throughout the training
        # (just compute one quadrant, as the distances are symmetric)
        # XXX maybe do other than squared Euclidean?
        dqd = np.fromfunction(lambda x, y: (x**2 + y**2)**0.5,
                             self.kshape, dtype='float')

        # for all iterations
        for it in xrange(1, self.niter + 1):
            # compute the neighborhood impact kernel for this iteration
            # has to be recomputed since kernel shrinks over time
            k = self._compute_influence_kernel(it, dqd)

            # for all training vectors
            for s in samples:
                # determine closest unit (as element coordinate)
                b = self._get_bmu(s)

                # train all units at once by unfolding the kernel (from the
                # single quadrant that is precomputed), cutting it to the
                # right shape and simply multiply it to the difference of target
                # and all unit weights....
                infl = np.vstack((
                        np.hstack((
                            # upper left
                            k[b[0]:0:-1, b[1]:0:-1],
                            # upper right
                            k[b[0]:0:-1, :self.kshape[1] - b[1]])),
                        np.hstack((
                            # lower left
                            k[:self.kshape[0] - b[0], b[1]:0:-1],
                            # lower right
                            k[:self.kshape[0] - b[0], :self.kshape[1] - b[1]]))
                               ))
                unit_deltas += infl[:,:,np.newaxis] * (s - self._K)

            # apply cumulative unit deltas
            self._K += unit_deltas

            if __debug__:
                debug("SOM", "Iteration %d/%d done: ||unit_deltas||=%g" %
                      (it, self.niter, np.sqrt(np.sum(unit_deltas **2))))

            # reset unit deltas
            unit_deltas.fill(0.)


    ##REF: Name was automagically refactored
    def _compute_influence_kernel(self, iter, dqd):
        """Compute the neighborhood kernel for some iteration.

        Parameters
        ----------
        iter : int
          The iteration for which to compute the kernel.
        dqd : array (nrows x ncolumns)
          This is one quadrant of Euclidean distances between Kohonen unit
          locations.
        """
        # compute radius decay for this iteration
        curr_max_radius = self.radius * np.exp(-1.0 * iter / self.iter_scale)

        # same for learning rate
        curr_lrate = self.lrate * np.exp(-1.0 * iter / self.iter_scale)

        # compute Gaussian influence kernel
        infl = np.exp((-1.0 * dqd) / (2 * curr_max_radius * iter))
        infl *= curr_lrate

        # hard-limit kernel to max radius
        # XXX is this really necessary?
        infl[dqd > curr_max_radius] = 0.

        return infl


    ##REF: Name was automagically refactored
    def _get_bmu(self, sample):
        """Returns the ID of the best matching unit.

        'best' is determined as minimal squared Euclidean distance between
        any units weight vector and some given target `sample`

        Parameters
        ----------
        sample : array
          Target sample.

        Returns
        -------
        tuple: (row, column)
        """
        # TODO expose distance function as parameter
        loc = np.argmin(((self.K - sample) ** 2).sum(axis=2))

        # assumes 2D Kohonen layer
        return (np.divide(loc, self.kshape[1]), loc % self.kshape[1])


    def _forward_data(self, data):
        """Map data from the IN dataspace into OUT space.

        Mapping is performs by simple determining the best matching Kohonen
        unit for each data sample.
        """
        return np.array([self._get_bmu(d) for d in data])


    def _reverse_data(self, data):
        """Reverse map data from OUT space into the IN space.
        """
        # simple transform into appropriate array slicing and
        # return the associated Kohonen unit weights
        return self.K[tuple(np.transpose(data))]


    def __repr__(self):
        s = Mapper.__repr__(self).rstrip(' )')
        # beautify
        if not s[-1] == '(':
            s += ' '
        s += 'kshape=%s, niter=%i, learning_rate=%f, iradius=%f)' \
                % (str(tuple(self.kshape)), self.niter, self.lrate,
                   self.radius)
        return s


    ##REF: Name was automagically refactored
    def _access_kohonen(self):
        """Provide access to the Kohonen layer.

        With some care.
        """
        if self._K is None:
            raise RuntimeError, \
                  'The SOM needs to be trained before access to the Kohonen ' \
                  'layer is possible.'

        return self._K


    K = property(fget=_access_kohonen)
