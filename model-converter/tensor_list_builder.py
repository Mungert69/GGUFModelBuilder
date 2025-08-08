import numpy as np
import argparse
import json
import sys
import re
import subprocess
from pathlib import Path

# Ordered list of quant levels (lowest precision to highest)
quant_levels = [
    "IQ1_S", "IQ1_M",
    "IQ2_XXS", "IQ2_XS", "IQ2_S", 
    "Q2_K", 
    "IQ3_XXS", "IQ3_S", 
    "Q3_K",
    "IQ4_XS","IQ4_NL", 
    "Q4_K",
    "Q5_K",
    "Q6_K",
    "Q8_0"
]

quant_substitutions = {
    "IQ2_M": "IQ2_S",  
    "IQ3_M": "IQ3_S", 
    "IQ3_XS": "IQ3_XXS",
    "Q2_K_S": "Q2_K",
    "Q3_K_S": "Q3_K",
    "Q4_K_S": "Q4_K",
    "Q5_K_S": "Q5_K",
    "Q6_K_S": "Q6_K",
    "Q2_K_M": "Q2_K",
    "Q3_K_M": "Q3_K",
    "Q4_K_M": "Q4_K",
    "Q5_K_M": "Q5_K",
    "Q6_K_M": "Q6_K",
}

def extract_layer_order(name: str) -> int:
    """
    Extract layer order from tensor name
    Example: 'blk.27.attn_k_norm' -> 27
    """
    match = re.search(r'blk\.(\d+)\.', name)
    return int(match.group(1)) if match else -1

def get_current_quant_types(gguf_file: str) -> tuple:
    """
    Get quantization types and find max layer order
    
    Returns:
        tuple: (quant_types dict, max_layer_order)
    """
    script_path = Path(__file__).parent / "get_gguf_tensor_info.py"
    output_file = Path("/tmp/gguf_quant_info.txt")  # Explicit path
    
    try:
        # Run script with explicit paths
        subprocess.run(
            [sys.executable, str(script_path), 
            str(Path(gguf_file).expanduser().resolve()),  # Handle ~ paths
            "-o", str(output_file)],
            check=True,
            timeout=30
        )
        
        # Read from explicit path
        quant_types = {}
        max_layer_order = -1
        
        with open(output_file, "r") as f:
            for line in f:
                name, quant = line.strip().split("=")
                quant_types[name] = quant
                
                # Find max layer order
                layer_order = extract_layer_order(name)
                max_layer_order = max(max_layer_order, layer_order)
                
        return quant_types, max_layer_order
        
    except Exception as e:
        print(f"Error: Failed to read quantization info. File location: {output_file}")
        print(f"Details: {str(e)}")
        sys.exit(1)

def normalize_layer_order(layer_order: int, max_layer_order: int) -> float:
    """
    Normalize layer order to 0-10 range
    
    Args:
        layer_order (int): Original layer order
        max_layer_order (int): Maximum layer order in the model
    
    Returns:
        float: Normalized layer order between 0 and 10
    """
    if max_layer_order <= 0:
        return 0
    
    return min(10 * (layer_order / max_layer_order), 10)

def is_match(value, pattern):
    """Check if value matches pattern (string or array)"""
    if isinstance(pattern, (list, tuple)):
        return value in pattern
    return value == pattern

def is_layer_match(layer_name: str, pattern: str) -> bool:
    """Improved wildcard matching for layer names with dot support"""
    if '*' in pattern:
        regex_pattern = '^' + re.escape(pattern).replace(r'\*', '.*') + '$'
        return re.fullmatch(regex_pattern, layer_name) is not None
    return pattern == layer_name

def determine_quant_tier(base_quant: str, 
    target_type: str,
    layer_name: str = None, 
    is_moe: bool = False, 
    layer_order: float = None, 
    quant_rules: list = None) -> tuple:
    """
    Improved quantization tier determination with wildcards and F32 protection
    """
    # Never bump F32 layers - keep original precision
    if base_quant == "F32":
        return (base_quant, "Keeping original F32 precision", False)
    

    try:
        target_idx = quant_levels.index(quant_substitutions.get(target_type, target_type))
    except ValueError:
        target_idx = quant_levels.index("Q4_K")
    
    default_return = (target_type, "No specific rule applied, using target type", False)
    
    if not quant_rules:
        return default_return
    
    total_bump = 0
    bump_reason = ""
    
    for rule in quant_rules:
        # Skip if target type doesn't match (supporting arrays)
        rule_base_types = rule.get('base_type', [])
        if isinstance(rule_base_types, str):
            rule_base_types = [rule_base_types]
        if target_type not in rule_base_types:
            continue
        
        # Skip if layer name doesn't match (with wildcard support)
        if 'layer_name' in rule:
            layer_patterns = rule['layer_name']
            if isinstance(layer_patterns, str):
                layer_patterns = [layer_patterns]
            
            layer_matched = False
            for pattern in layer_patterns:
                if is_layer_match(layer_name, pattern):
                    layer_matched = True
                    break
            
            if not layer_matched:
                continue
        
        # Apply bumps
        base_bump = rule.get('bump_experts', rule.get('bump', 0)) if is_moe else rule.get('bump', 0)
        total_bump += int(base_bump)
        
        # Layer order bumps
        if layer_order is not None and 'bump_order_low' in rule:
            bump_order_low = rule.get('bump_order_low', float('-inf'))
            bump_order_high = rule.get('bump_order_high', float('inf'))
            
            if layer_order <= bump_order_low or layer_order >= bump_order_high:
                order_bump = rule.get('bump_order_experts_val', rule.get('bump_order_val', 0)) if is_moe else rule.get('bump_order_val', 0)
                total_bump += int(order_bump)
                bump_reason += f"Layer order bump: {order_bump} "
    
    if total_bump == 0:
        return default_return
    
    new_idx = min(target_idx + total_bump, len(quant_levels) - 1)
    full_reason = f"Bumped from {target_type} by {total_bump} levels"
    if layer_name:
        full_reason += f" for {layer_name}"
    if bump_reason:
        full_reason += f" ({bump_reason.strip()})"
    
    return quant_levels[new_idx], full_reason, True

def apply_precision_override_rule(
    tensor_name, suggested_quant, reason, bump_applied, quant_rules, precision_override,
    is_moe=None, layer_order=None
):
    """
    Checks for override_types rules and applies the precision override if the tensor matches.
    Returns (suggested_quant, reason, bump_applied).
    """
    if not precision_override:
        return suggested_quant, reason, bump_applied

    for rule in quant_rules:
        override_types = rule.get("override_types", [])
        if precision_override not in override_types:
            continue

        # Check layer_name match (with wildcard support)
        layer_patterns = rule.get("layer_name", [])
        if isinstance(layer_patterns, str):
            layer_patterns = [layer_patterns]
        if not any(is_layer_match(tensor_name, pattern) for pattern in layer_patterns):
            continue

        # Check experts field if present
        if "experts" in rule:
            if is_moe is None or bool(is_moe) != bool(rule["experts"]):
                continue

        # Check order_low/order_high if present
        if layer_order is not None and "order_low" in rule and "order_high" in rule:
            if not (rule["order_low"] <= layer_order <= rule["order_high"]):
                continue

        # All checks passed, apply override
        return (
            precision_override,
            f"Override: {precision_override} for {tensor_name} by rule",
            True,
        )
    return suggested_quant, reason, bump_applied

def process_quantization(gguf_file: str, quant_rules_file: str, target_type: str, is_moe: bool = False, precision_override: str = None):
    """
    Process quantization for a model based on JSON rules
    
    Args:
        gguf_file (str): Path to the GGUF model file
        quant_rules_file (str): Path to JSON quantization rules
        target_type (str): Target quantization type
        is_moe (bool): Whether this is a Mixture of Experts model
    """
    # Load quantization rules
    with open(quant_rules_file, 'r') as f:
        quant_rules = json.load(f).get('rules', [])
    
    # Get current quantization types and max layer order
    current_quants, max_layer_order = get_current_quant_types(gguf_file)
    
    # Track suggestions
    quant_suggestions = []
    
    # Process each tensor
    for name, current_quant in current_quants.items():
        # Skip changing quant type for mxfp4
        if "mxfp4" in str(current_quant).lower():
            continue
        # Extract layer order
        layer_order = extract_layer_order(name)
        
        # Normalize layer order to 0-10 range
        normalized_layer_order = normalize_layer_order(layer_order, max_layer_order)
        # Normalize target_type
        normalized_target_type = quant_substitutions.get(target_type, target_type)

        # Determine suggested quantization
        suggested_quant, reason, bump_applied = determine_quant_tier(
            base_quant=current_quant,
            target_type=normalized_target_type,
            layer_name=name,
            is_moe=is_moe,
            layer_order=normalized_layer_order,
            quant_rules=quant_rules
        )
        # Apply override_types rules if precision_override is set
        suggested_quant, reason, bump_applied = apply_precision_override_rule(
            name, suggested_quant, reason, bump_applied, quant_rules, precision_override,
            is_moe=is_moe, layer_order=layer_order
        )


        
        # Only add suggestion if it's different from current
        if bump_applied:
            quant_suggestions.append((name, suggested_quant, reason))
    # Sort by layer number before printing
    def layer_sort_key(item):
        return extract_layer_order(item[0])

    quant_suggestions.sort(key=layer_sort_key)

    # Print results
    print("\n=== Quantization Suggestions ===")
    #for name, quant, reason in quant_suggestions:
    #    print(f"Tensor: {name}")
    #    print(f"  Current: {current_quants[name]}")
    #    print(f"  Suggested: {quant}")
    #    print(f"  Reason: {reason}\n")
    
    # Generate tensor-type arguments
    #print("=== Suggested --tensor-type arguments (copy-ready) ===")
    tensor_args = " ".join([f"--tensor-type {name}={quant}" for name, quant, _ in quant_suggestions])
    return tensor_args

def main():
    parser = argparse.ArgumentParser(
        description="Determine model quantization based on JSON rules"
    )
    parser.add_argument("gguf_file", help="GGUF model file to analyze")
    parser.add_argument("quant_rules", help="JSON file with quantization rules")
    parser.add_argument("target_type", help="Target quantization type")
    parser.add_argument("--moe", action="store_true", 
                        help="Indicate if this is a Mixture of Experts model")
    
    args = parser.parse_args()
    
    tensor_args = process_quantization(
        gguf_file=args.gguf_file,
        quant_rules_file=args.quant_rules,
        target_type=args.target_type,
        is_moe=args.moe
    )
    print(tensor_args)

if __name__ == "__main__":
    main()
