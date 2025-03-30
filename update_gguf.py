#!/usr/bin/env python3
import logging
import argparse
import os
import sys
from pathlib import Path

# Necessary to load the local gguf package
if "NO_LOCAL_GGUF" not in os.environ and (Path(__file__).parent.parent.parent.parent / 'gguf-py').exists():
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gguf import GGUFReader  # noqa: E402
from gguf import GGUFValueType
logger = logging.getLogger("gguf-set-metadata")

def set_custom_metadata(reader: GGUFReader) -> None:
    """Set the specific metadata fields we want to add/update"""
    metadata_updates = {
        "general.quantized_by": "Mungert",
        "general.repo_url": "https://huggingface.co/mungert",
        "general.sponsor_url": "https://freenetworkmonitor.click"
    }
    
    for key, value in metadata_updates.items():
        field = reader.get_field(key)
        if field is not None:
            # Field exists, update it
            if field.types[0] == GGUFValueType.STRING:
                new_value = value.encode("utf-8")
            else:
                handler = reader.gguf_scalar_to_np.get(field.types[0])
                if handler is None:
                    logger.error(f'! Unsupported type for field {key}')
                    continue
                new_value = handler(value)
            
            field.parts[field.data[0]] = [new_value]
            logger.info(f'* Updated field {key}')
        else:
            # Field doesn't exist, we would need to add it
            # Note: Adding new fields requires GGUFWriter functionality
            logger.warning(f'! Field {key} does not exist (adding new fields not implemented)')

def set_metadata(reader: GGUFReader, args: argparse.Namespace) -> None:
    if args.custom:
        set_custom_metadata(reader)
        return
    
    field = reader.get_field(args.key)
    if field is None:
        logger.error(f'! Field {repr(args.key)} not found')
        sys.exit(1)
        
    if field.types[0] == GGUFValueType.STRING:
        new_value = args.value.encode("utf-8")
    else:
        handler = reader.gguf_scalar_to_np.get(field.types[0]) if field.types else None
        if handler is None:
            logger.error(f'! Unsupported type for field {repr(args.key)}')
            sys.exit(1)
        new_value = handler(args.value)

    current_value = field.parts[field.data[0]][0]
    logger.info(f'* Preparing to change field {repr(args.key)} from {current_value} to {new_value}')
    
    if current_value == new_value:
        logger.info(f'- Key {repr(args.key)} already set to requested value {current_value}')
        sys.exit(0)
    if args.dry_run:
        sys.exit(0)
    if not args.force:
        logger.warning('*** Warning *** Warning *** Warning **')
        logger.warning('* Changing fields in a GGUF file can make it unusable. Proceed at your own risk.')
        logger.warning('* Enter exactly YES if you are positive you want to proceed:')
        response = input('YES, I am sure> ')
        if response != 'YES':
            logger.info("You didn't enter YES. Okay then, see ya!")
            sys.exit(0)
            
    field.parts[field.data[0]] = [new_value]
    logger.info('* Field changed. Successful completion.')

def main() -> None:
    parser = argparse.ArgumentParser(description="Set values in GGUF file metadata")
    parser.add_argument("model", type=str, help="GGUF format model filename")
    parser.add_argument("--key", type=str, help="Metadata key to set (use with --value)")
    parser.add_argument("--value", type=str, help="Metadata value to set (use with --key)")
    parser.add_argument("--custom", action="store_true", help="Set predefined custom metadata fields")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually change anything")
    parser.add_argument("--force", action="store_true", help="Change the field without confirmation")
    parser.add_argument("--verbose", action="store_true", help="Increase output verbosity")

    args = parser.parse_args()

    if not args.custom and (not args.key or not args.value):
        parser.error("Either --custom or both --key and --value must be specified")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    logger.info(f'* Loading: {args.model}')
    reader = GGUFReader(args.model, 'r' if args.dry_run else 'r+')
    
    if args.custom:
        set_custom_metadata(reader)
    else:
        set_metadata(reader, args)

if __name__ == '__main__':
    main()
