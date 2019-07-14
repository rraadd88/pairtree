import argparse
import os
import numpy as np
import scipy.integrate
import warnings
import random
import multiprocessing
import sys

import common
import pairwise
import inputparser
import tree_sampler
import clustermaker
import resultserializer
import hyperparams

def _parse_args():
  parser = argparse.ArgumentParser(
    description='LOL HI THERE',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
  )
  parser.add_argument('--verbose', action='store_true')
  parser.add_argument('--seed', dest='seed', type=int)
  parser.add_argument('--parallel', dest='parallel', type=int, default=None)
  parser.add_argument('--params', dest='params_fn')
  parser.add_argument('--trees-per-chain', dest='trees_per_chain', type=int, default=2000)
  parser.add_argument('--tree-chains', dest='tree_chains', type=int, default=None)
  parser.add_argument('--burnin', dest='burnin', type=float, default=(1/3), help='Fraction of samples to discard from beginning of each chain')
  parser.add_argument('--thinned-frac', dest='thinned_frac', type=float, default=1)
  parser.add_argument('--phi-iterations', dest='phi_iterations', type=int, default=10000)
  parser.add_argument('--phi-fitter', dest='phi_fitter', choices=('graddesc', 'rprop', 'projection', 'proj_rprop'), default='rprop')
  parser.add_argument('--only-build-tensor', dest='only_build_tensor', action='store_true')

  parser.add_argument('--rho', type=float, default=5,
    help='Weight of mutrel fit term when selecting node to move within tree, such that we prefer nodes with high mutrel error')
  parser.add_argument('--psi', type=float, default=3,
    help='How strongly peaked the depth term is in the beta-PDF-like depth score, such that higher values will favour nodes at the precise requested depth')
  parser.add_argument('--theta', type=float, default=4,
    help='Weight of ancestral pairwise probabilities when determining potential parent probability distribution for selected node when doing tree updates, such that nodes with high ancestral probability are preferred as parents')
  parser.add_argument('--kappa', type=float, default=1,
    help='Weight of tree depth when determining potential parent probability distribution for selected node when doing tree updates, such that nodes deeper in the existing tree are preferred as parents')

  parser.add_argument('ssm_fn')
  parser.add_argument('results_fn')
  args = parser.parse_args()
  return args

def _init_hyperparams(args):
  hparams = (
    'rho',
    'psi',
    'theta',
    'kappa',
  )
  for K in hparams:
    V = getattr(args, K)
    # Checking that the key already exists in `hyperparams` isn't necessary.
    # But it's useful because it enforces treating `hyperparams` as a central
    # listing of all hyperparams.
    assert hasattr(hyperparams, K)
    setattr(hyperparams, K, V)

def main():
  np.set_printoptions(linewidth=400, precision=3, threshold=sys.maxsize, suppress=True)
  np.seterr(divide='raise', invalid='raise')
  warnings.simplefilter('ignore', category=scipy.integrate.IntegrationWarning)

  args = _parse_args()
  _init_hyperparams(args)
  common.debug.DEBUG = args.verbose

  # Note that multiprocessing.cpu_count() returns number of logical cores, so
  # if you're using a hyperthreaded CPU, this will be more than the number of
  # physical cores you have.
  parallel = args.parallel if args.parallel is not None else multiprocessing.cpu_count()
  tree_chains = args.tree_chains if args.tree_chains is not None else parallel

  if args.seed is not None:
    seed = args.seed
  else:
    # Maximum seed is 2**32 - 1.
    seed = np.random.randint(2**32)
  np.random.seed(seed)
  random.seed(seed)

  variants = inputparser.load_ssms(args.ssm_fn)
  params = inputparser.load_params(args.params_fn)
  logprior = {'garbage': -np.inf, 'cocluster': -np.inf}

  if os.path.exists(args.results_fn):
    results = resultserializer.load(args.results_fn)
  else:
    results = {'seed': seed}

  if 'clustrel_posterior' not in results:
    if 'clusters' in params and 'garbage' in params:
      supervars, results['clustrel_posterior'], results['clustrel_evidence'], results['clusters'], results['garbage'] = clustermaker.use_pre_existing(
        variants,
        logprior,
        parallel,
        params['clusters'],
        params['garbage'],
      )
    else:
      if 'mutrel_posterior' not in results:
        results['mutrel_posterior'], results['mutrel_evidence'] = pairwise.calc_posterior(variants, logprior=logprior, rel_type='variant', parallel=parallel)
        resultserializer.save(results, args.results_fn)
      clustermaker._plot.prefix = os.path.basename(args.ssm_fn).split('.')[0]
      supervars, results['clustrel_posterior'], results['clustrel_evidence'], results['clusters'], results['garbage'] = clustermaker.cluster_and_discard_garbage(
        variants,
        results['mutrel_posterior'],
        results['mutrel_evidence'],
        logprior,
        parallel,
      )

    resultserializer.save(results, args.results_fn)
  else:
    supervars = clustermaker.make_cluster_supervars(results['clusters'], variants)

  if args.only_build_tensor:
    sys.exit()

  superclusters = clustermaker.make_superclusters(supervars)
  # Add empty initial cluster, which serves as tree root.
  superclusters.insert(0, [])

  if 'adjm' not in results:
    if 'structures' not in params:
      results['adjm'], results['phi'], results['llh'] = tree_sampler.sample_trees(
        results['clustrel_posterior'],
        supervars,
        superclusters,
        args.trees_per_chain,
        args.burnin,
        tree_chains,
        args.thinned_frac,
        args.phi_fitter,
        args.phi_iterations,
        seed,
        parallel,
      )
      resultserializer.save(results, args.results_fn)
    else:
      adjls = [inputparser.load_structure(struct) for struct in params['structures']]
      adjms = [common.convert_adjlist_to_adjmatrix(adjl) for adjl in adjls]
      results['adjm'], results['phi'], results['llh'] = tree_sampler.use_existing_structures(
        adjms,
        supervars,
        superclusters,
        args.phi_fitter,
        args.phi_iterations,
        parallel
      )
      resultserializer.save(results, args.results_fn)

if __name__ == '__main__':
  main()
