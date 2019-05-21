import common
import numpy as np

def fit_phis(adj, superclusters, supervars, method, iterations, parallel):
  key = (hash(adj.tobytes()), iterations)
  if key not in fit_phis.cache:
    fit_phis.cache[key] = _fit_phis(adj, superclusters, supervars, method, iterations, parallel)
    fit_phis.cache_misses += 1
  else:
    fit_phis.cache_hits += 1
  return fit_phis.cache[key]

fit_phis.cache = {}
fit_phis.cache_hits = 0
fit_phis.cache_misses = 0

def _fit_phis(adj, superclusters, supervars, method, iterations, parallel):
  # Calling `import` on each function call should be cheap, as Python caches a
  # reference to the module after the first load.
  if method in ('graddesc', 'rprop'):
    import phi_fitter_iterative
    eta = phi_fitter_iterative.fit_etas(adj, superclusters, supervars, method, iterations, parallel)

  elif method == 'projection':
    import phi_fitter_projection
    eta = phi_fitter_projection.fit_etas(adj, superclusters, supervars)

  elif method == 'proj_rprop':
    import phi_fitter_projection
    import phi_fitter_iterative
    eta_proj = phi_fitter_projection.fit_etas(adj, superclusters, supervars)
    eta = phi_fitter_iterative.fit_etas(adj, superclusters, supervars, 'rprop', iterations, parallel, eta_init=eta_proj)

  else:
    raise Exception('Unknown phi fitter %s' % method)

  assert np.allclose(1, np.sum(eta, axis=0))
  Z = common.make_ancestral_from_adj(adj)
  phi = np.dot(Z, eta)
  return (phi, eta)
