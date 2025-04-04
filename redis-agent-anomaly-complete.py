#!/usr/bin/env python3
# redis_agent/anomaly.py - Anomaly detection for Redis Enterprise

import logging
import threading
import time
import os
import pickle
import numpy as np
from typing import Dict, List, Any, Tuple
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("redis-agent.anomaly")

# Key metrics for detecting anomalies
ANOMALY_METRICS = [
    "latency_ms",
    "memory_used_percent",
    "hit_rate", 
    "ops_per_second",
    "connected_clients",
    "rejected_connections",
    "evicted_keys"
]

class AnomalyDetector:
    """Detect anomalies in Redis metrics using ML models"""
    
    def __init__(self, core_agent):
        """Initialize the anomaly detection module.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config
        self.models = {}  # instance_uid -> dict with model and scaler
        self.metrics_data = {}  # instance_uid -> dict with feature data
        self.training_thread = None
        self.running = False
        self.lock = threading.RLock()
    
    def initialize(self):
        """Initialize anomaly detection models."""
        # Create models directory if it doesn't exist
        model_path = Path(self.config.model_path)
        model_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize models for each instance
        for instance in self.config.instances:
            self._init_model(instance.uid, instance.name)
            
            # Initialize metrics data
            self.metrics_data[instance.uid] = {
                "features": [],
                "timestamps": []
            }
    
    def _init_model(self, instance_uid: str, instance_name: str):
        """Initialize or load anomaly detection model for an instance."""
        model_file = Path(self.config.model_path) / f"{instance_uid}_model.pkl"
        scaler_file = Path(self.config.model_path) / f"{instance_uid}_scaler.pkl"
        
        try:
            if model_file.exists() and scaler_file.exists():
                # Load existing model
                with open(model_file, 'rb') as f:
                    model = pickle.load(f)
                with open(scaler_file, 'rb') as f:
                    scaler = pickle.load(f)
                
                logger.info(f"Loaded anomaly detection model for instance {instance_name}")
                is_trained = True
            else:
                # Create new model
                model = IsolationForest(
                    n_estimators=100,
                    max_samples="auto",
                    contamination=0.05,  # Expecting 5% of data to be anomalous
                    random_state=42
                )
                scaler = StandardScaler()
                is_trained = False
                logger.info(f"Created new anomaly detection model for instance {instance_name}")
            
            self.models[instance_uid] = {
                "model": model,
                "scaler": scaler,
                "is_trained": is_trained,
                "last_training": model_file.stat().st_mtime if model_file.exists() else 0
            }
            
        except Exception as e:
            logger.error(f"Error initializing anomaly detection model for {instance_name}: {e}")
            # Create default model on error
            self.models[instance_uid] = {
                "model": IsolationForest(contamination=0.05, random_state=42),
                "scaler": StandardScaler(),
                "is_trained": False,
                "last_training": 0
            }
    
    def start(self):
        """Start the training thread."""
        if self.training_thread and self.training_thread.is_alive():
            logger.warning("Training thread already running")
            return
        
        self.running = True
        self.training_thread = threading.Thread(
            target=self._training_loop,
            daemon=True
        )
        self.training_thread.start()
        logger.info("Anomaly detection training thread started")
    
    def stop(self):
        """Stop the training thread."""
        self.running = False
        if self.training_thread and self.training_thread.is_alive():
            self.training_thread.join(timeout=5)
        logger.info("Anomaly detection training thread stopped")
        
        # Save models on shutdown
        self._save_models()
    
    def _training_loop(self):
        """Main loop for periodically training models."""
        # Initial sleep to allow metrics collection
        time.sleep(300)  # 5 minutes
        
        while self.running:
            try:
                # Train models for all instances
                for instance in self.config.instances:
                    self._train_model(instance.uid, instance.name)
                
                # Save models
                self._save_models()
                
                # Sleep for 1 hour before next training
                for _ in range(36):  # Check every 100 seconds if should stop
                    if not self.running:
                        break
                    time.sleep(100)
            
            except Exception as e:
                logger.error(f"Error in training loop: {e}")
                time.sleep(600)  # 10 minutes on error
    
    def _train_model(self, instance_uid: str, instance_name: str):
        """Train the anomaly detection model for an instance."""
        with self.lock:
            if instance_uid not in self.models or instance_uid not in self.metrics_data:
                logger.warning(f"No model or metrics data for instance {instance_name}")
                return
            
            features = self.metrics_data[instance_uid]["features"]
            
            # Need at least 100 data points for training
            if len(features) < 100:
                logger.info(f"Not enough data to train model for {instance_name} ({len(features)} samples)")
                return
            
            try:
                # Convert to numpy array
                X = np.array(features)
                
                # Fit scaler
                scaler = self.models[instance_uid]["scaler"]
                X_scaled = scaler.fit_transform(X)
                
                # Train model
                model = self.models[instance_uid]["model"]
                model.fit(X_scaled)
                
                # Update model info
                self.models[instance_uid]["is_trained"] = True
                self.models[instance_uid]["last_training"] = time.time()
                
                logger.info(f"Trained anomaly detection model for {instance_name} with {len(features)} samples")
                
            except Exception as e:
                logger.error(f"Error training model for {instance_name}: {e}")
    
    def _save_models(self):
        """Save all models to disk."""
        for instance_uid, model_info in self.models.items():
            if not model_info["is_trained"]:
                continue
            
            try:
                model_file = Path(self.config.model_path) / f"{instance_uid}_model.pkl"
                scaler_file = Path(self.config.model_path) / f"{instance_uid}_scaler.pkl"
                
                # Save model
                with open(model_file, 'wb') as f:
                    pickle.dump(model_info["model"], f)
                
                # Save scaler
                with open(scaler_file, 'wb') as f:
                    pickle.dump(model_info["scaler"], f)
                
                logger.info(f"Saved model for instance {instance_uid}")
                
            except Exception as e:
                logger.error(f"Error saving model for instance {instance_uid}: {e}")
    
    def process_metrics(self, instance_uid: str, dc_name: str, metrics: Dict[str, Any]):
        """Process new metrics for anomaly detection.
        
        Args:
            instance_uid: Instance UID
            dc_name: Datacenter name
            metrics: Dictionary of metrics
        """
        # Extract features for anomaly detection
        features = self._extract_features(metrics)
        
        with self.lock:
            # Store features for training
            if instance_uid in self.metrics_data:
                self.metrics_data[instance_uid]["features"].append(features)
                self.metrics_data[instance_uid]["timestamps"].append(metrics["timestamp"])
                
                # Limit history size (keep last 10000 samples)
                max_samples = 10000
                if len(self.metrics_data[instance_uid]["features"]) > max_samples:
                    self.metrics_data[instance_uid]["features"] = self.metrics_data[instance_uid]["features"][-max_samples:]
                    self.metrics_data[instance_uid]["timestamps"] = self.metrics_data[instance_uid]["timestamps"][-max_samples:]
        
        # Detect anomalies
        is_anomaly, score, details = self._detect_anomaly(instance_uid, features)
        
        # Update health status with anomaly information
        if is_anomaly:
            # Get current health status
            health_status = self.core.get_health_status()[instance_uid][dc_name]
            
            # Update anomaly information
            health_status.is_anomaly = True
            health_status.anomaly_score = score
            health_status.consecutive_anomalies += 1
            
            # Update status based on severity
            if score > 0.9:  # Severe anomaly
                health_status.status = "failing"
                if score > 0.95:  # Critical anomaly
                    health_status.can_serve_traffic = False
            elif health_status.status == "healthy":
                health_status.status = "degraded"
            
            # Update health status
            self.core.update_health_status(instance_uid, dc_name, health_status)
            
            # Log anomaly
            logger.warning(f"Anomaly detected for {instance_uid} in {dc_name} (score: {score:.2f})")
            
            # Check if we should create an alert
            if score > self.config.anomaly_threshold and health_status.consecutive_anomalies >= 3:
                self._create_anomaly_alert(instance_uid, dc_name, score, details, metrics)
    
    def _extract_features(self, metrics: Dict[str, Any]) -> List[float]:
        """Extract features for anomaly detection from metrics."""
        features = []
        
        # Extract standard metrics
        for metric_name in ANOMALY_METRICS:
            if metric_name in metrics:
                # Normalize some values to a reasonable range
                if metric_name == "ops_per_second":
                    features.append(min(metrics[metric_name] / 10000.0, 1.0))  # Normalize to [0,1]
                elif metric_name == "connected_clients":
                    features.append(min(metrics[metric_name] / 1000.0, 1.0))   # Normalize to [0,1]
                else:
                    features.append(float(metrics[metric_name]))
            else:
                # Use default value if metric is missing
                features.append(0.0)
        
        # Add derived metrics if available
        if "api_avg_latency_ms" in metrics:
            features.append(float(metrics["api_avg_latency_ms"]))
        else:
            features.append(0.0)
        
        return features
    
    def _detect_anomaly(self, instance_uid: str, features: List[float]) -> Tuple[bool, float, Dict[str, float]]:
        """Detect if the metrics represent an anomaly.
        
        Args:
            instance_uid: Instance UID
            features: List of feature values
            
        Returns:
            Tuple of (is_anomaly, anomaly_score, details)
        """
        with self.lock:
            if instance_uid not in self.models:
                return False, 0.0, {}
            
            model_info = self.models[instance_uid]
            
            # Skip detection if model is not trained
            if not model_info["is_trained"]:
                return False, 0.0, {}
            
            try:
                # Scale features
                X = np.array([features])
                X_scaled = model_info["scaler"].transform(X)
                
                # Predict
                score = model_info["model"].decision_function(X_scaled)[0]
                
                # Convert score to anomaly score (0=normal, 1=anomaly)
                # Isolation Forest returns negative scores for anomalies
                anomaly_score = 1.0 - (1.0 + score) / 2.0
                
                # Determine if this is an anomaly
                threshold = self.config.anomaly_threshold
                is_anomaly = anomaly_score > threshold
                
                # Generate details about which metrics contributed to the anomaly
                details = {}
                if is_anomaly:
                    # This is a simple approach - in a production system,
                    # you would use more sophisticated methods like SHAP values
                    # to determine feature importance
                    
                    # Calculate z-scores for each feature
                    feature_values = []
                    for i in range(len(self.metrics_data[instance_uid]["features"])):
                        feature_values.append(self.metrics_data[instance_uid]["features"][i])
                    
                    if feature_values:
                        feature_array = np.array(feature_values)
                        means = np.mean(feature_array, axis=0)
                        stds = np.std(feature_array, axis=0)
                        
                        for i, metric_name in enumerate(ANOMALY_METRICS):
                            if i < len(features) and i < len(means) and i < len(stds):
                                if stds[i] > 0:
                                    z_score = abs((features[i] - means[i]) / stds[i])
                                    # Consider features with high z-score as contributors
                                    if z_score > 2.0:
                                        details[metric_name] = min(z_score / 5.0, 1.0)  # Normalize to [0,1]
                
                return is_anomaly, anomaly_score, details
                
            except Exception as e:
                logger.error(f"Error detecting anomaly for {instance_uid}: {e}")
                return False, 0.0, {}
    
    def _create_anomaly_alert(self, instance_uid: str, dc_name: str, score: float, 
                             details: Dict[str, float], metrics: Dict[str, Any]):
        """Create an alert for a detected anomaly."""
        if not hasattr(self.core, "alerting"):
            return
        
        # Find instance name
        instance_name = "unknown"
        for instance in self.config.instances:
            if instance.uid == instance_uid:
                instance_name = instance.name
                break
        
        # Determine severity
        severity = "warning"
        if score > 0.95:
            severity = "critical"
        elif score > 0.9:
            severity = "error"
        
        # Create alert details
        alert_details = {
            "instance_uid": instance_uid,
            "instance_name": instance_name,
            "datacenter": dc_name,
            "anomaly_score": score,
            "metrics": {
                "latency_ms": metrics.get("latency_ms", 0),
                "memory_used_percent": metrics.get("memory_used_percent", 0),
                "hit_rate": metrics.get("hit_rate", 0),
                "ops_per_second": metrics.get("ops_per_second", 0),
                "connected_clients": metrics.get("connected_clients", 0),
                "rejected_connections": metrics.get("rejected_connections", 0),
                "evicted_keys": metrics.get("evicted_keys", 0)
            },
            "contributing_factors": details
        }
        
        # Create alert message
        message = f"Anomaly detected in Redis instance {instance_name} (DC: {dc_name})"
        
        # Send alert
        self.core.alerting.send_alert(
            alert_type="anomaly_detected",
            severity=severity,
            message=message,
            details=alert_details
        )
