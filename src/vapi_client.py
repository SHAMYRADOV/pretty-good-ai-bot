import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class VAPIClient:
    """Client for interacting with VAPI AI API"""
    
    def __init__(self):
        self.private_key = os.getenv('VAPI__PRIVATE_API_KEY')
        self.public_key = os.getenv('VAPI__PUBLIC_API_KEY')
        self.phone_number_id = os.getenv('VAPI_PHONE_NUMBER_ID')
        self.base_url = "https://api.vapi.ai"
        
        if not self.private_key:
            raise ValueError("VAPI__PRIVATE_API_KEY not found in environment variables")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for VAPI API requests"""
        return {
            "Authorization": f"Bearer {self.private_key}",
            "Content-Type": "application/json"
        }
    
    async def create_assistant(self, 
                             name: str, 
                             system_prompt: str, 
                             voice_settings: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a new assistant with specific persona"""
        
        assistant_config = {
            "name": name,
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.7,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    }
                ]
            },
            "voice": voice_settings or {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Default voice
                "stability": 0.5,
                "similarityBoost": 0.75
            },
            "firstMessage": "Hi there.",
            "recordingEnabled": True,
            "maxDurationSeconds": 420,
            "silenceTimeoutSeconds": 30,
            "backgroundDenoisingEnabled": True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/assistant",
                headers=self._get_headers(),
                json=assistant_config
            ) as response:
                if response.status == 201:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to create assistant: {response.status} - {error_text}")
    
    async def make_outbound_call(self, 
                                assistant_id: str, 
                                phone_number: str,
                                metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an outbound call using the specified assistant"""
        
        call_config = {
            "assistantId": assistant_id,
            "phoneNumberId": self.phone_number_id,
            "customer": {
                "number": phone_number
            }
        }
        
        if metadata:
            call_config["metadata"] = metadata
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/call",
                headers=self._get_headers(),
                json=call_config
            ) as response:
                if response.status == 201:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to make call: {response.status} - {error_text}")
    
    async def get_call_details(self, call_id: str) -> Dict[str, Any]:
        """Get details about a specific call"""
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/call/{call_id}",
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get call details: {response.status} - {error_text}")
    
    async def wait_for_call_completion(self, call_id: str, timeout: int = 300) -> Dict[str, Any]:
        """Wait for call to complete and return final details"""
        
        start_time = datetime.now()
        
        while True:
            call_details = await self.get_call_details(call_id)
            
            if call_details.get('status') in ['completed', 'failed', 'ended']:
                return call_details
            
            # Check timeout
            elapsed = (datetime.now() - start_time).seconds
            if elapsed > timeout:
                raise TimeoutError(f"Call {call_id} did not complete within {timeout} seconds")
            
            # Wait before checking again
            await asyncio.sleep(5)
    
    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant (cleanup)"""
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/assistant/{assistant_id}",
                headers=self._get_headers()
            ) as response:
                return response.status == 200
