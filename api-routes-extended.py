# Add these routes to the existing routes.py file

# ----- Client Log Endpoints -----

@router.get("/client-errors/{instance_uid}", summary="Get client error analysis for an instance")
async def get_client_errors(
    instance_uid: str,
    minutes: int = 30,
    api_key: str = Depends(verify_api_key)
):
    """Get client error analysis from ELK for a specific Redis instance."""
    if not hasattr(core_agent, "elk_client"):
        raise HTTPException(status_code=501, detail="ELK client module not available")
    
    # Check if instance exists
    instance_exists = False
    for instance in core_agent.config.instances:
        if instance.uid == instance_uid:
            instance_exists = True
            break
    
    if not instance_exists:
        raise HTTPException(status_code=404, detail=f"Instance {instance_uid} not found")
    
    # Get client error analysis
    error_analysis = core_agent.elk_client.analyze_client_errors(instance_uid, minutes)
    
    return error_analysis

# ----- AI Recommendation Endpoints -----

@router.get("/ai-recommendations/{instance_uid}", summary="Get AI recommendations for an instance")
async def get_ai_recommendations(
    instance_uid: str,
    api_key: str = Depends(verify_api_key)
):
    """Get recent AI recommendations for a specific Redis instance."""
    if not hasattr(core_agent, "failover") or not hasattr(core_agent.failover, "ai_recommendations"):
        raise HTTPException(status_code=501, detail="AI recommendations not available")
    
    # Check if instance exists
    instance_exists = False
    for instance in core_agent.config.instances:
        if instance.uid == instance_uid:
            instance_exists = True
            break
    
    if not instance_exists:
        raise HTTPException(status_code=404, detail=f"Instance {instance_uid} not found")
    
    # Get recommendations
    recommendations = core_agent.failover.ai_recommendations.get(instance_uid, [])
    
    return {"recommendations": recommendations}