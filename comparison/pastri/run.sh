#!/bin/bash
#module load gnu-parallel

BASEDIR=~/work/pairtree
SCRIPTDIR=$(dirname "$(readlink -f "$0")")
JOBDIR=/tmp
PAIRTREE_INPUTS_DIR=$BASEDIR/scratch/inputs/sims.pairtree
BATCH=sims.pastri.informative
INDIR=$BASEDIR/scratch/inputs/$BATCH
OUTDIR=$BASEDIR/scratch/results/$BATCH
PARALLEL=80
NUM_ITERS=10000
PASTRI_DIR=$HOME/.apps/pastri

function convert_inputs {
  mkdir -p $INDIR

  for ssmfn in $PAIRTREE_INPUTS_DIR/*.ssm; do
    sampid=$(basename $ssmfn | cut -d. -f1)
    echo "python3 $SCRIPTDIR/convert_inputs.py " \
      "--uniform-proposal" \
      "$PAIRTREE_INPUTS_DIR/$sampid.ssm" \
      "$PAIRTREE_INPUTS_DIR/$sampid.params.json" \
      "$INDIR/$sampid.counts" \
      "$INDIR/$sampid.proposal"
  done | parallel -j$PARALLEL --halt 1
}

function run_pastri {
  mkdir -p $OUTDIR

  for countsfn in $INDIR/*.counts; do
    runid=$(basename $countsfn | cut -d. -f1)
    jobname="steph_pastri_${runid}"

    (
      # Must source ~/.bash_host_specific to get PATH set properly for
      # Miniconda.
      echo "source $HOME/.bash_host_specific && " \
        "cd $OUTDIR && " \
        "python2 $PASTRI_DIR/src/RunPASTRI.py" \
        "--output_prefix $runid" \
        "--num_iters $NUM_ITERS" \
        "$INDIR/${runid}.counts" \
        "$INDIR/${runid}.proposal" \
        ">$runid.stdout" \
        "2>$runid.stderr"
    ) 
  done | parallel -j$PARALLEL --joblog $SCRATCH/tmp/$BATCH.log
}

function get_F_and_C {
  for treesfn in $OUTDIR/*.trees; do
    runid=$(basename $treesfn | cut -d. -f1)
    # Trees in $treesfn are ranked by likelihood. `get_F_and_C.py` takes tree
    # rank as a parameter. Thus, if we count N trees with LH > 0, we know their
    # ranks are [0, 1, ..., N-1].
    valid_count=$(cat $treesfn | grep '^>' | grep -v -- '-inf$' | wc -l)
    for idx in $(seq $valid_count); do
      echo "source $HOME/.bash_host_specific && " \
        "cd $OUTDIR && " \
        "python2 $PASTRI_DIR/src/get_F_and_C.py" \
        "-i $idx" \
        "-o $OUTDIR/$runid" \
        "$INDIR/${runid}.counts" \
        "$treesfn" \
        "$OUTDIR/${runid}.fsamples"
    done
  done | parallel -j$PARALLEL > /dev/null
}

function convert_outputs {
  for tree_weights in llh uniform; do
    for treesfn in $OUTDIR/*.trees; do
      runid=$(basename $treesfn | cut -d. -f1)
      echo "source $HOME/.bash_host_specific && " \
        "cd $OUTDIR && " \
        "OMP_NUM_THREADS=1 python3 $SCRIPTDIR/convert_outputs.py" \
        "--weight-trees-by $tree_weights" \
        "--trees-mutrel $OUTDIR/$runid.pastri_trees_$tree_weights.mutrel.npz" \
        "$runid" \
        "$PAIRTREE_INPUTS_DIR/$runid.params.json" \
        "$treesfn"
    done
  done | parallel -j$PARALLEL > /dev/null
}

function main {
  #convert_inputs
  #run_pastri
  #get_F_and_C
  convert_outputs
}

main
