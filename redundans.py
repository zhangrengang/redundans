#!/usr/bin/env python
desc="""Heterozygous genome assembly pipeline.
It consists of three steps:
1. assembly reduction
2. scaffolding
3. gap closing

Note, FASTQ libraries need to be

PREREQUISITIES:
- genome assembly (fasta)
- BLAT
- BWA
- Biopython
- SSPACE3

To be done:
- check if files exist
- libra
"""
epilog="""Author:
l.p.pryszcz@gmail.com

Mizerow/Warsaw, 17/10/2014
"""

import os, resource, sys, glob
from datetime import datetime
import numpy as np

from fasta2homozygous import fasta2homozygous
from fastq2sspace import fastq2sspace
from fastq2insert_size import fastq2insert_size

from fasta_stats import fasta_stats

def timestamp():
    """Return formatted date-time string"""
    return "\n%s\n[%s] "%("#"*50, datetime.ctime(datetime.now()))

def symlink(file1, file2):
    """Create symbolic link taking care of real path."""
    if not os.path.isfile(file2):
        os.symlink(os.path.join(os.path.realpath(os.path.curdir), file1), file2)

def get_orientation(pairs, fq1, fq2):
    """Return orientation of paired reads, either FF, FR, RF or RR.
    Warn if major orientation is represented by less than 90% of reads.
    """
    orientations = ('FF', 'FR', 'RF', 'RR')
    maxc = max(pairs)
    # get major orientation
    maxci = pairs.index(maxc)
    orientation = orientations[maxci]
    # get frac of total reads
    maxcfrac = 100.0 * maxc / sum(pairs)
    if maxcfrac < 90:
        info = "[WARNING] Poor quality: Major orientation (%s) represent %s%s of pairs in %s - %s: %s\n"
        sys.stderr.write(info%(orientation, maxcfrac, '%', fq1, fq2, str(pairs)))
    return orientation 

def get_libraries(fastq, reducedFname, mapq, threads, limit, verbose):
    """Return libraries"""
    # get libraries statistics using 1% of mapped read limit
    libdata = fastq2insert_size(sys.stderr, fastq, reducedFname, mapq, threads, \
                                limit/100, verbose)
    # separate paired-end & mate pairs
    ## also separate 300 and 600 paired-ends
    libraries = []
    # add libraries strating from lowest insert size
    for fq1, fq2, ismedian, ismean, isstd, pairs in sorted(libdata, key=lambda x: x[3]):
        # add new library set if 
        if not libraries or ismedian > 1.5*libraries[-1][4][0]:
            # libnames, libFs, libRs, orientations, libIS, libISStDev
            libraries.append([[], [], [], [], [], []])
            i = 1
        # add libname & fastq files
        libraries[-1][0].append("lib%s"%i)
        libraries[-1][1].append(open(fq1))
        libraries[-1][2].append(open(fq2))
        # orientation
        orientation = get_orientation(pairs, fq1, fq2)
        libraries[-1][3].append(orientation)
        # insert size information
        libraries[-1][4].append(int(ismean))
        stdfrac = isstd / ismean
        libraries[-1][5].append(stdfrac)
        # update counter
        i += 1
    return libraries
    
def run_scaffolding(outdir, scaffoldsFname, fastq, reducedFname, mapq, threads, \
                    joins, limit, iters, sspacebin, verbose, lib=""):
    """Execute scaffolding step"""
    # get libraries
    libraries = get_libraries(fastq, reducedFname, mapq, threads, limit, verbose)
        
    # run scaffolding using libraries with increasing insert size in multiple iterations
    pout = reducedFname    
    for i, (libnames, libFs, libRs, orientations, libIS, libISStDev) in enumerate(libraries, 1):
        for j in range(1, iters+1):
            if verbose:
                sys.stderr.write(" iteration %s.%s ...\n"%(i,j))
            out = "_sspace.%s.%s"%(i, j)
            lib = ""
            # run fastq scaffolding
            fastq2sspace(out, open(pout), lib, libnames, libFs, libRs, orientations, \
                         libIS, libISStDev, threads, mapq, limit, joins, \
                         sspacebin, verbose=0)
            # store out info
            pout = os.path.join(out, "_sspace.%s.%s"%(i, j)+".final.scaffolds.fasta")
            
    # create symlink to final scaffolds or pout
    symlink(pout, scaffoldsFname)
    
def redundants(fastq, fasta, outdir, mapq, threads, identity, overlap, minLength, \
               joins, limit, iters, sspacebin, reduction=1, scaffolding=1, gapclosing=1, \
               verbose=1, log=sys.stderr):
    """Launch redundans pipeline."""
    # redirect stderr
    #sys.stderr = log
    
    # prepare outdir or quit if exists
    if os.path.isdir(outdir):
        sys.stderr.write("Directory %s exists!\n"%outdir)
        #sys.exit(1)
    else:
        os.makedirs(outdir)

    # check if all files exists
    #_check_files(log, fasta, fastq)
    
    # REDUCTION
    contigsFname = os.path.join(outdir, "contigs.fa")
    reducedFname = os.path.join(outdir, "contigs.reduced.fa")
    # link contigs & genome
    symlink(fasta, contigsFname)
    if reduction:
        if verbose:
            sys.stderr.write("%sReduction...\n"%timestamp())
            sys.stderr.write("#file name\tgenome size\tcontigs\theterozygous size\t[%]\theterozygous contigs\t[%]\tidentity [%]\tpossible joins\thomozygous size\t[%]\thomozygous contigs\t[%]\n")
        with open(reducedFname, "w") as out:
            fasta2homozygous(out, open(contigsFname), identity, overlap, minLength)
    else:
        symlink(contigsFname, reducedFname)

    # SCAFFOLDING
    scaffoldsFname = os.path.join(outdir, "scaffolds.fa")
    if scaffolding:
        if verbose:
            sys.stderr.write("%sScaffolding...\n"%timestamp())
        run_scaffolding(outdir, scaffoldsFname, fastq, reducedFname, mapq, threads, \
                        joins, limit, iters, sspacebin, verbose)
    else:
        symlink(reducedFname, scaffoldsFname)
        
    # GAP CLOSING
    nogapsFname = os.path.join(outdir, "scaffolds.nogaps.fa")
    if gapclosing:
        if verbose:
            sys.stderr.write("%sGap closing...\n"%timestamp())
        #run_gapclosing()
        symlink(scaffoldsFname, nogapsFname)
    else:
        symlink(scaffoldsFname, nogapsFname)

    # FASTA STATS
    if verbose:
        sys.stderr.write("%sReporting statistics...\n"%timestamp())
    scaffoldFastas = sorted(glob.glob("_sspace*/*.final.scaffolds.fasta"))
    sys.stderr.write('#fname\tcontigs\tbases\tGC [%]\tcontigs >1kb\tbases in contigs >1kb\tN50\tN90\tNs\tlongest\n')
    for fn in [contigsFname, reducedFname] + scaffoldFastas + [scaffoldsFname, nogapsFname]:
        sys.stderr.write(fasta_stats(open(fn)))
        
def main():
    import argparse
    usage   = "%(prog)s -v" #usage=usage, 
    parser  = argparse.ArgumentParser(description=desc, epilog=epilog, \
                                      formatter_class=argparse.RawTextHelpFormatter)
  
    parser.add_argument("-v", dest="verbose",  default=False, action="store_true", help="verbose")    
    parser.add_argument('--version', action='version', version='1.0a')   
    parser.add_argument("-i", "--fastq", nargs="+", 
                        help="FASTQ PE/MP files")
    parser.add_argument("-f", "--fasta", 
                        help="assembly FASTA file")
    parser.add_argument("-o", "--outdir",  default=".", 
                        help="output directory")
    parser.add_argument("-q", "--mapq",    default=10, type=int, 
                        help="min mapping quality for variants [%(default)s]")
    parser.add_argument("-t", "--threads", default=2, type=int, 
                        help="max threads to run [%(default)s]")
    parser.add_argument("--log",           default=None, type=argparse.FileType('w'), 
                        help="output log to [stderr]")
    redu = parser.add_argument_group('Reduction options')
    redu.add_argument("--identity",        default=0.8, type=float,
                      help="min. identity [%(default)s]")
    redu.add_argument("--overlap",         default=0.75, type=float,
                      help="min. overlap  [%(default)s]")
    redu.add_argument("--minLength",       default=200, type=int, 
                      help="min. contig length [%(default)s]")
    ##missing redu options
    scaf = parser.add_argument_group('Scaffolding options')
    scaf.add_argument("-j", "--joins",  default=5, type=int, 
                      help="min k pairs to join contigs [%(default)s]")
    scaf.add_argument("-l", "--limit",  default=5000000, type=int, 
                      help="align at most l reads [%(default)s]")
    scaf.add_argument("-iters",         default=2, type=int, 
                      help="scaffolding iterations per library  [%(default)s]")
    scaf.add_argument("--sspacebin",    default="~/src/SSPACE/SSPACE_Standard_v3.0.pl", 
                       help="SSPACE path  [%(default)s]")
    gaps = parser.add_argument_group('Gap closing options')
    #gaps.add_argument("-l", "--limit",  default=7e, type=int, 
    #                  help="align l reads [%(default)s]")
    skip = parser.add_argument_group('Skip below steps (all performed by default)')
    skip.add_argument('--reduction',   action='store_false', default=True)   
    skip.add_argument('--scaffolding', action='store_false', default=True)   
    skip.add_argument('--gapclosing',  action='store_false', default=True)   
    
    o = parser.parse_args()
    if o.verbose:
        sys.stderr.write("Options: %s\n"%str(o))
        
    # initialise pipeline
    redundants(o.fastq, o.fasta, o.outdir, o.mapq, o.threads, \
               o.identity, o.overlap, o.minLength, \
               o.joins, o.limit, o.iters, o.sspacebin, \
               o.reduction, o.scaffolding, o.gapclosing, \
               o.verbose, o.log)

if __name__=='__main__': 
    t0 = datetime.now()
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nCtrl-C pressed!      \n")
    #except IOError as e:
    #    sys.stderr.write("I/O error({0}): {1}\n".format(e.errno, e.strerror))
    dt = datetime.now()-t0
    sys.stderr.write("#Time elapsed: %s\n"%dt)
