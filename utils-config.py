# redis_agent/utils/config.py
"""Configuration utilities for Redis Enterprise agent."""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Apply environment variable overrides
        apply_env_overrides(config)
        
        return config
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")

def apply_env_overrides(config: Dict[str, Any]):
    """
    Apply environment variable overrides to configuration.
    
    Args:
        config: Configuration dictionary to update
    """
    # Azure OpenAI overrides
    if "azure_openai" in config:
        if "AZURE_OPENAI_API_KEY" in os.environ:
            config["azure_openai"]["api_key"] = os.environ["AZURE_OPENAI_API_KEY"]
        
        if "AZURE_OPENAI_ENDPOINT" in os.environ:
            config["azure_openai"]["endpoint"] = os.environ["AZURE_OPENAI_ENDPOINT"]
    
    # ELK overrides
    if "elk" in config:
        if "ELASTICSEARCH_URL" in os.environ:
            config["elk"]["url"] = os.environ["ELASTICSEARCH_URL"]
        
        if "ELASTICSEARCH_USERNAME" in os.environ:
            config["elk"]["username"] = os.environ["ELASTICSEARCH_USERNAME"]
        
        if "ELASTICSEARCH_PASSWORD" in os.environ:
            config["elk"]["password"] = os.environ["ELASTICSEARCH_PASSWORD"]
    
    # AWS overrides
    if "dns_config" in config:
        if "AWS_ACCESS_KEY_ID" in os.environ:
            config["dns_config"]["aws_access_key"] = os.environ["AWS_ACCESS_KEY_ID"]
        
        if "AWS_SECRET_ACCESS_KEY" in os.environ:
            config["dns_config"]["aws_secret_key"] = os.environ["AWS_SECRET_ACCESS_KEY"]
        
        if "AWS_REGION" in os.environ:
            config["dns_config"]["aws_region"] = os.environ["AWS_REGION"]
    
    # Redis password overrides
    for instance in config.get("instances", []):
        env_var = f"REDIS_PASSWORD_{instance.get('uid', '')}"
        if env_var in os.environ:
            instance["password"] = os.environ[env_var]
    
    # API key override
    if "api" in config and "API_KEY" in os.environ:
        config["api"]["api_key"] = os.environ["API_KEY"]

def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration structure and required fields.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if configuration is valid, False otherwise
    """
    # Check for required sections
    required_sections = ["instances", "datacenters"]
    for section in required_sections:
        if section not in config:
            print(f"Missing required configuration section: {section}")
            return False
    
    # Validate instance configurations
    for instance in config.get("instances", []):
        if "name" not in instance or "uid" not in instance or "endpoints" not in instance:
            print(f"Instance missing required fields: {instance}")
            return False
        
        if not instance.get("endpoints"):
            print(f"Instance has no endpoints: {instance.get('name')}")
            return False
    
    # Validate datacenter configurations
    for dc_name, dc_config in config.get("datacenters", {}).items():
        if "name" not in dc_config:
            print(f"Datacenter {dc_name} missing required field: name")
            return False
    
    # Validate Azure OpenAI configuration if enabled
    if config.get("use_azure_openai", False):
        if "azure_openai" not in config:
            print("Azure OpenAI is enabled but configuration is missing")
            return False
        
        azure_config = config.get("azure_openai", {})
        required_azure_fields = ["api_key", "endpoint", "model"]
        for field in required_azure_fields:
            if field not in azure_config:
                print(f"Azure OpenAI configuration missing required field: {field}")
                return False
    
    # Validate ELK configuration if enabled
    if config.get("use_elk", False):
        if "elk" not in config:
            print("ELK is enabled but configuration is missing")
            return False
        
        elk_config = config.get("elk", {})
        if "url" not in elk_config:
            print("ELK configuration missing required field: url")
            return False
    
    # Validate DNS failover configuration if enabled
    if config.get("failover_provider") == "dns":
        if "dns_config" not in config:
            print("DNS failover provider is enabled but configuration is missing")
            return False
        
        dns_config = config.get("dns_config", {})
        if config.get("dns_provider") == "route53":
            if "zone_id" not in dns_config:
                print("Route53 configuration missing required field: zone_id")
                return False
        
        if not dns_config.get("records"):
            print("DNS configuration has no records defined")
            return False
    
    return True