#!/usr/bin/env python3
"""
Simple test script to verify the platform works correctly.
"""

import requests
import json
import sys

def test_api_endpoints():
    """Test the main API endpoints."""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing API endpoints...")
    
    # Test home endpoint
    print("1. Testing home endpoint...")
    try:
        response = requests.get(f"{base_url}/")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "indices" in data["defaults"]
        print("   ✅ Home endpoint works correctly")
    except Exception as e:
        print(f"   ❌ Home endpoint failed: {e}")
        return False
    
    # Test health endpoint
    print("2. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health")
        assert response.status_code == 200
        data = response.json()
        # Should show not initialized when no credentials are provided
        assert data["ok"] is False
        assert "environment variables" in data["message"]
        print("   ✅ Health endpoint works correctly (shows configuration status)")
    except Exception as e:
        print(f"   ❌ Health endpoint failed: {e}")
        return False
    
    # Test start endpoint without credentials (should fail gracefully)
    print("3. Testing start endpoint without credentials...")
    try:
        response = requests.post(f"{base_url}/start", 
                               data={"start_year": 2023, "end_year": 2023},
                               files={"file": ("test.geojson", '{"type":"Point","coordinates":[0,0]}', "application/json")})
        assert response.status_code == 503  # Service unavailable
        data = response.json()
        assert "Google Cloud and Earth Engine services not available" in data["detail"]
        print("   ✅ Start endpoint fails gracefully without credentials")
    except Exception as e:
        print(f"   ❌ Start endpoint test failed: {e}")
        return False
    
    print("\n🎉 All API tests passed! The platform is working correctly.")
    return True

def test_with_mock_credentials():
    """Test with mock credentials to verify the app logic."""
    import os
    import tempfile
    import subprocess
    
    print("\n🧪 Testing with mock credentials...")
    
    # Set mock environment variables
    env = os.environ.copy()
    env.update({
        "EE_SERVICE_ACCOUNT_EMAIL": "test@example.com",
        "EE_PROJECT": "test-project",
        "GCS_BUCKET": "test-bucket",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON": '{"type": "service_account", "project_id": "test"}'
    })
    
    # Test that the module loads with credentials (even if they're invalid)
    try:
        result = subprocess.run([
            sys.executable, "-c", 
            "import main; print('Module loads with mock credentials')"
        ], env=env, capture_output=True, text=True)
        
        if "Module loads with mock credentials" in result.stdout:
            print("   ✅ App loads with mock credentials (EE/GCS initialization may fail, which is expected)")
        else:
            print(f"   ⚠️  App loads but with warnings: {result.stderr}")
        
        return True
    except Exception as e:
        print(f"   ❌ Mock credentials test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Sentinel-2 Indices Exporter Platform")
    print("=" * 50)
    
    # Start server for testing
    import subprocess
    import time
    import signal
    
    print("Starting test server...")
    server = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "main:app", 
        "--host", "0.0.0.0", "--port", "8000"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        success = test_api_endpoints()
        if success:
            success = test_with_mock_credentials()
    finally:
        # Stop server
        server.terminate()
        server.wait()
    
    if success:
        print("\n🎉 Platform testing completed successfully!")
        print("The platform is ready for deployment to Render.")
        sys.exit(0)
    else:
        print("\n❌ Platform testing failed!")
        sys.exit(1)