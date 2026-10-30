"""CLI entry point:  python main.py [--input data/sample/customers.csv] [--output-dir outputs]"""
import argparse
import sys

from src.duplicate_detection import MatchConfig
from src.ingestion import IngestionError
from src.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer duplicate detection pipeline")
    parser.add_argument("--input", default="data/sample/customers.csv")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--auto-merge-threshold", type=float, default=MatchConfig.auto_merge_threshold)
    parser.add_argument("--name-block-prefix", type=int, default=MatchConfig.name_block_prefix,
                        help="letters of first/last name used for name blocking (1=loose, 2=tight)")
    args = parser.parse_args()

    cfg = MatchConfig(auto_merge_threshold=args.auto_merge_threshold,
                      name_block_prefix=args.name_block_prefix)
    try:
        run_pipeline(args.input, args.output_dir, args.log_dir, cfg)
    except IngestionError:
        return 2  # already logged; file rejected
    return 0


if __name__ == "__main__":
    sys.exit(main())
