#!/usr/bin/env python3
"""Plan non-overlapping seed+trajectory-index ranges; does not prove RNG independence."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validate.validate_cycles import replicate_seeds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-count', type=int, required=True)
    parser.add_argument('--replicates', type=int, required=True)
    parser.add_argument('--first-seed', type=int, required=True)
    args = parser.parse_args(argv)
    try: seeds = replicate_seeds(args.sample_count, args.replicates, args.first_seed)
    except ValueError as error: parser.error(str(error))
    print(json.dumps({'schema_version': 1, 'sample_count': args.sample_count, 'seeds': seeds,
                      'assumption': 'engine trajectory streams use seed + trajectory index; verify engine version',
                      'independence_verified': False}))


if __name__ == '__main__':
    main()
