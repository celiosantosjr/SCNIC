import shutil
import glob
import os

import general
import pysurvey as ps
from functools import partial
from scipy.spatial.distance import squareform
import numpy as np
import pandas as pd
from pysurvey import SparCC as sparcc

__author__ = 'shafferm'


def biom_to_df(table):
    return pd.DataFrame(np.transpose(table.matrix_data.todense()), index=table.ids(), columns=table.ids(axis="observation"))


def permute_w_replacement(frame):
    '''
    ***STOLEN FROM https://bitbucket.org/yonatanf/pysurvey and adapted***
    Permute the frame values across the given axis.
    Create simulated dataset were the counts of each component (column)
    in each sample (row), are randomly sampled from the all the
    counts of that component in all samples.

    Parameters
    ----------
    frame : DataFrame
        Frame to permute.
    axis : {0, 1}
        - 0 - Permute row values across columns
        - 1 - Permute column values across rows

    Returns
    -------
    Permuted DataFrame (new instance).
    '''
    from numpy.random import randint
    s = frame.shape[0]
    fun = lambda x: x.values[randint(0,s,(1,s))][0]
    perm = frame.apply(fun, axis=0)
    return perm


def make_bootstraps(counts, nperm):
    '''
    ***STOLEN FROM https://bitbucket.org/yonatanf/pysurvey and adapted***
    Make n simulated datasets used to get pseudo p-values.
    Simulated datasets are generated by assigning each OTU in each sample
    an abundance that is randomly drawn (w. replacement) from the
    abundances of the OTU in all samples.
    Simulated datasets are either written out as txt files.

    Parameters
    ----------
    counts : DataFrame
        Inferred correlations whose p-values are to be computed.
    nperm : int
        Number of permutations to produce.
    '''
    bootstraps = []
    for i in xrange(nperm):
        bootstraps.append(permute_w_replacement(counts))
    return bootstraps


def boostrapped_correlation(bootstrap, cor, df):
    in_cor = ps.basis_corr(permute_w_replacement(df), oprint=False)[0]
    in_cor = squareform(in_cor, checks=False)
    return np.abs(in_cor) >= cor

def sparcc_correlation(table):
    # convert to pandas dataframe
    df = biom_to_df(table)

    # calculate correlations
    cor, cov = ps.basis_corr(df, oprint=False)

     # generate correls
    correls = list()
    for i in xrange(len(cor.index)):
        for j in xrange(i+1, len(cor.index)):
            correls.append([str(cor.index[i]), str(cor.index[j]), cor.iat[i, j]])

    header = ['feature1', 'feature2', 'r']
    return correls, header

def co_to_correls(cor):
    # generate correls
    correls = list()
    for i in xrange(len(cor.index)):
        for j in xrange(i+1, len(cor.index)):
            correls.append([str(cor.index[i]), str(cor.index[j]), cor.iat[i, j]])

    header = ['feature1', 'feature2', 'r']
    return correls, header

def sparcc_correlations_single(table, p_adjust=general.bh_adjust, bootstraps=100):
    """"""
    # convert to pandas dataframe
    df = biom_to_df(table)

    # calculate correlations
    cor, cov = ps.basis_corr(df, oprint=False)

    # calculate p-values
    abs_cor = np.abs(squareform(cor, checks=False))
    n_sig = np.zeros(abs_cor.shape)
    for i in xrange(bootstraps):
        n_sig[boostrapped_correlation(i, cor, df)] += 1
    p_vals = squareform(1.*n_sig/bootstraps, checks=False)

    # generate correls
    correls = list()
    for i in xrange(len(cor.index)):
        for j in xrange(i+1, len(cor.index)):
            correls.append([str(cor.index[i]), str(cor.index[j]), cor.iat[i, j], p_vals[i, j]])

    # adjust p-value if desired
    if p_adjust is not None:
        p_adjusted = p_adjust([i[3] for i in correls])
        for i in xrange(len(correls)):
            correls[i].append(p_adjusted[i])

    header = ['feature1', 'feature2', 'r', 'p']
    if p_adjust is not None:
        header.append('adjusted_p')

    return correls, header

def sparcc_correlations_multi(table, p_adjust=general.bh_adjust, bootstraps=100, procs=None):
    """"""
    # setup
    import multiprocessing

    if procs is None:
        if multiprocessing.cpu_count() == 1:
            procs=1
        else:
            procs = multiprocessing.cpu_count()-1

    if procs == 1:
        sparcc_correlations_single(table, p_adjust, bootstraps)

    pool = multiprocessing.Pool(procs)
    print "Number of processors used: " + str(procs)

    # convert to pandas dataframe
    df = biom_to_df(table)

    # calculate correlations
    cor, cov = ps.basis_corr(df, oprint=False)

    # take absolute value of all values in cor for calculating two-sided p-value
    abs_cor = np.abs(squareform(cor, checks=False))
    # create an empty array of significant value counts in same shape as abs_cor
    n_sig = np.zeros(abs_cor.shape)

    # make partial function for use in multiprocessing
    pfun = partial(boostrapped_correlation, cor=abs_cor, df=df)
    # run multiprocessing
    multi_results = pool.map(pfun, range(bootstraps))
    pool.close()
    pool.join()

    # find number of significant results across all bootstraps
    for i in multi_results:
        n_sig[i] += 1
    p_vals = squareform(1.*n_sig/bootstraps, checks=False)

    # generate correls array
    correls = list()
    for i in xrange(len(cor.index)):
        for j in xrange(i+1, len(cor.index)):
            correls.append([str(cor.index[i]), str(cor.index[j]), cor.iat[i, j], p_vals[i, j]])

    # adjust p-value if desired
    if p_adjust is not None:
        p_adjusted = p_adjust([i[3] for i in correls])
        for i in xrange(len(correls)):
            correls[i].append(p_adjusted[i])

    header = ['feature1', 'feature2', 'r', 'p']
    if p_adjust is not None:
        header.append('adjusted_p')

    return correls, header
