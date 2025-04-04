# redis_agent/utils/metrics.py
"""Utility functions for processing metrics data."""

import time
import math
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

def normalize_metrics(metrics: Dict[str, Any], thresholds: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize raw metrics to values between 0 and 1 for anomaly detection.
    
    Args:
        metrics: Dictionary of raw metrics
        thresholds: Dictionary of threshold values for normalization
        
    Returns:
        Dictionary of normalized metrics
    """
    normalized = {}
    
    # Response time (0-1 where 1 is bad)
    if "latency_ms" in metrics:
        latency_threshold = thresholds.get("latency_ms", 100)
        normalized["latency_ms"] = min(1.0, metrics["latency_ms"] / latency_threshold)
    
    # Memory usage (0-1 where 1 is 100% used)
    if "memory_used_percent" in metrics:
        normalized["memory_used_percent"] = metrics["memory_used_percent"] / 100.0
    
    # Hit rate (0-1 where 1 is 100% hit rate, inverted for anomaly detection)
    if "hit_rate" in metrics:
        # Invert so 1 is bad (0% hit rate)
        normalized["hit_rate"] = 1.0 - metrics["hit_rate"]
    
    # Operations per second (normalize to 0-1)
    if "ops_per_second" in metrics:
        ops_threshold = thresholds.get("ops_per_second", 10000)
        normalized["ops_per_second"] = min(1.0, metrics["ops_per_second"] / ops_threshold)
    
    # Connected clients (normalize to 0-1)
    if "connected_clients" in metrics:
        clients_threshold = thresholds.get("connected_clients", 1000)
        normalized["connected_clients"] = min(1.0, metrics["connected_clients"] / clients_threshold)
    
    # Rejected connections (any > 0 is bad)
    if "rejected_connections" in metrics:
        rejected_threshold = thresholds.get("rejected_connections", 10)
        normalized["rejected_connections"] = min(1.0, metrics["rejected_connections"] / rejected_threshold)
    
    # Evicted keys (normalize to 0-1)
    if "evicted_keys" in metrics:
        evicted_threshold = thresholds.get("evicted_keys", 1000)
        normalized["evicted_keys"] = min(1.0, metrics["evicted_keys"] / evicted_threshold)
    
    # Redis Enterprise specific metrics
    if "avg_latency" in metrics:
        avg_latency_threshold = thresholds.get("avg_latency", 10)
        normalized["avg_latency"] = min(1.0, metrics["avg_latency"] / avg_latency_threshold)
    
    if "total_req" in metrics:
        total_req_threshold = thresholds.get("total_req", 10000)
        normalized["total_req"] = min(1.0, metrics["total_req"] / total_req_threshold)
    
    return normalized

def calculate_metric_trend(metrics_history: List[Dict[str, Any]], metric_name: str, window_minutes: int = 30) -> Optional[float]:
    """
    Calculate the trend (slope) of a specific metric over time.
    
    Args:
        metrics_history: List of metric dictionaries with timestamps
        metric_name: Name of the metric to analyze
        window_minutes: Time window in minutes for the trend calculation
        
    Returns:
        Slope of the metric trend (change per minute), or None if not enough data
    """
    if not metrics_history or len(metrics_history) < 2:
        return None
    
    # Calculate cutoff time
    now = time.time()
    cutoff_time = now - (window_minutes * 60)
    
    # Filter metrics by time window
    recent_metrics = [m for m in metrics_history if m["timestamp"] >= cutoff_time]
    
    # Need at least 2 data points
    if len(recent_metrics) < 2:
        return None
    
    # Extract timestamps and values
    timestamps = []
    values = []
    
    for metric in recent_metrics:
        if metric_name in metric:
            timestamps.append(metric["timestamp"])
            values.append(metric[metric_name])
    
    # Need at least 2 valid data points
    if len(timestamps) < 2:
        return None
    
    # Convert timestamps to minutes from now for better scale
    minutes_ago = [(now - ts) / 60 for ts in timestamps]
    
    # Calculate trend using numpy
    try:
        slope, _ = np.polyfit(minutes_ago, values, 1)
        
        # Negate slope because we're using minutes ago (descending)
        return -slope
    except:
        return None

def detect_metric_anomalies(metrics_history: List[Dict[str, Any]], metric_name: str, z_threshold: float = 3.0) -> List[Dict[str, Any]]:
    """
    Detect anomalies in a specific metric using z-score.
    
    Args:
        metrics_history: List of metric dictionaries
        metric_name: Name of the metric to analyze
        z_threshold: Z-score threshold for anomaly detection
        
    Returns:
        List of anomalous metrics with z-scores
    """
    if not metrics_history or len(metrics_history) < 10:
        return []
    
    # Extract values
    values = []
    
    for metric in metrics_history:
        if metric_name in metric:
            values.append(metric[metric_name])
    
    # Need enough data points
    if len(values) < 10:
        return []
    
    # Calculate mean and standard deviation
    mean = np.mean(values)
    std = np.std(values)
    
    # If std is too small, avoid division by zero
    if std < 0.0001:
        return []
    
    # Find anomalies
    anomalies = []
    
    for metric in metrics_history:
        if metric_name in metric:
            z_score = abs(metric[metric_name] - mean) / std
            
            if z_score > z_threshold:
                anomalies.append({
                    "timestamp": metric["timestamp"],
                    "value": metric[metric_name],
                    "z_score": z_score,
                    "metric": metric_name
                })
    
    return anomalies

def calculate_metric_statistics(metrics_history: List[Dict[str, Any]], metric_name: str) -> Dict[str, float]:
    """
    Calculate statistics for a specific metric.
    
    Args:
        metrics_history: List of metric dictionaries
        metric_name: Name of the metric to analyze
        
    Returns:
        Dictionary of statistics
    """
    if not metrics_history:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None
        }
    
    # Extract values
    values = []
    
    for metric in metrics_history:
        if metric_name in metric:
            values.append(metric[metric_name])
    
    # Calculate statistics
    stats = {
        "count": len(values)
    }
    
    if values:
        stats.update({
            "min": np.min(values),
            "max": np.max(values),
            "mean": np.mean(values),
            "median": np.median(values),
            "std": np.std(values)
        })
    else:
        stats.update({
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None
        })
    
    return stats

def smooth_metric_data(metrics_history: List[Dict[str, Any]], metric_name: str, window_size: int = 5) -> List[float]:
    """
    Apply smoothing to metric data using moving average.
    
    Args:
        metrics_history: List of metric dictionaries
        metric_name: Name of the metric to smooth
        window_size: Size of the moving average window
        
    Returns:
        List of smoothed values
    """
    if not metrics_history:
        return []
    
    # Extract values
    values = []
    
    for metric in metrics_history:
        if metric_name in metric:
            values.append(metric[metric_name])
    
    # Apply moving average
    smoothed = []
    
    for i in range(len(values)):
        start_idx = max(0, i - window_size + 1)
        window = values[start_idx:i+1]
        smoothed.append(sum(window) / len(window))
    
    return smoothed

def downsample_metrics(metrics_history: List[Dict[str, Any]], target_points: int) -> List[Dict[str, Any]]:
    """
    Downsample metrics data to a target number of points.
    
    Args:
        metrics_history: List of metric dictionaries
        target_points: Target number of data points
        
    Returns:
        Downsampled list of metric dictionaries
    """
    if not metrics_history or len(metrics_history) <= target_points:
        return metrics_history
    
    # Calculate step size
    step = len(metrics_history) / target_points
    
    # Select points
    downsampled = []
    
    for i in range(target_points):
        idx = min(len(metrics_history) - 1, int(i * step))
        downsampled.append(metrics_history[idx])
    
    return downsampled

def format_metrics_for_chart(metrics_history: List[Dict[str, Any]], metric_name: str) -> Dict[str, List]:
    """
    Format metrics data for charting.
    
    Args:
        metrics_history: List of metric dictionaries
        metric_name: Name of the metric to format
        
    Returns:
        Dictionary with timestamps and values
    """
    timestamps = []
    values = []
    
    for metric in metrics_history:
        if metric_name in metric:
            timestamps.append(metric["timestamp"] * 1000)  # Convert to milliseconds for JS
            values.append(metric[metric_name])
    
    return {
        "timestamps": timestamps,
        "values": values
    }
