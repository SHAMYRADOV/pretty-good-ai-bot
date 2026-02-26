import os
import json
import asyncio
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class CallStorage:
    """Handles storage of call data, transcripts, and bug analysis"""
    
    def __init__(self, runs_directory: str = "./runs"):
        self.runs_dir = Path(runs_directory)
        self.runs_dir.mkdir(exist_ok=True)
        self.api_key = os.getenv('VAPI__PRIVATE_API_KEY')
        
        # Create subdirectories
        (self.runs_dir / "transcripts").mkdir(exist_ok=True)
        (self.runs_dir / "recordings").mkdir(exist_ok=True)
        (self.runs_dir / "analysis").mkdir(exist_ok=True)
        (self.runs_dir / "reports").mkdir(exist_ok=True)
    
    def log_cost(self, call_id: str, call_details: Dict[str, Any], call_number: int = 0,
                 scenario_name: str = "unknown") -> None:
        """Append cost breakdown for a call to runs/cost_log.json"""

        cost_file = self.runs_dir / "cost_log.json"

        # Load existing log
        if cost_file.exists():
            with open(cost_file, 'r') as f:
                cost_log = json.load(f)
        else:
            cost_log = {"calls": [], "totals": {}}

        # Extract every cost field VAPI may return
        cost_total = call_details.get("cost", 0) or 0
        cost_breakdown = call_details.get("costBreakdown", {}) or {}

        entry = {
            "call_number": call_number,
            "scenario": scenario_name,
            "call_id": call_id,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": call_details.get("duration", 0) or 0,
            "status": call_details.get("status"),
            "cost_total": cost_total,
            "cost_breakdown": {
                "transport": cost_breakdown.get("transport", 0) or 0,
                "stt": cost_breakdown.get("stt", 0) or 0,
                "llm": cost_breakdown.get("llm", 0) or 0,
                "tts": cost_breakdown.get("tts", 0) or 0,
                "vapi": cost_breakdown.get("vapi", 0) or 0,
            },
            # Grab any extra top-level cost-related keys
            "analysis_cost": call_details.get("analysisCost", 0) or 0,
        }

        cost_log["calls"].append(entry)

        # Recompute running totals
        totals = {
            "total_calls": len(cost_log["calls"]),
            "total_cost": round(sum(c["cost_total"] for c in cost_log["calls"]), 4),
            "total_duration_seconds": sum(c["duration_seconds"] for c in cost_log["calls"]),
            "by_category": {
                "transport": round(sum(c["cost_breakdown"]["transport"] for c in cost_log["calls"]), 4),
                "stt": round(sum(c["cost_breakdown"]["stt"] for c in cost_log["calls"]), 4),
                "llm": round(sum(c["cost_breakdown"]["llm"] for c in cost_log["calls"]), 4),
                "tts": round(sum(c["cost_breakdown"]["tts"] for c in cost_log["calls"]), 4),
                "vapi": round(sum(c["cost_breakdown"]["vapi"] for c in cost_log["calls"]), 4),
            }
        }
        cost_log["totals"] = totals

        with open(cost_file, 'w') as f:
            json.dump(cost_log, f, indent=2, default=str)

        print(f"💰 Cost: ${cost_total:.4f} | Running total: ${totals['total_cost']:.4f}")

    def download_recording(self, call_id: str, recording_url: str, base_name: str = "") -> Optional[str]:
        """Download call recording from VAPI using API key auth"""
        
        if not recording_url:
            print("⚠️  No recording URL available")
            return None
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.get(recording_url, headers=headers)
            
            if resp.status_code == 200 and len(resp.content) > 100:
                filename = f"{base_name}.wav" if base_name else f"recording_{call_id[:8]}.wav"
                filepath = self.runs_dir / "recordings" / filename
                
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                
                size_mb = len(resp.content) / (1024 * 1024)
                print(f"🎙️  Recording saved: {filepath} ({size_mb:.1f} MB)")
                return str(filepath)
            else:
                print(f"⚠️  Could not download recording: HTTP {resp.status_code}")
                return None
        except Exception as e:
            print(f"⚠️  Error downloading recording: {e}")
            return None
    
    def save_call_data(self, call_id: str, call_details: Dict[str, Any], 
                      persona: Dict[str, Any], call_number: int = 0,
                      scenario_name: str = "unknown") -> str:
        """Save complete call data and return filename"""
        
        # Unified naming: call_01_appointment, call_02_elderly, etc.
        base_name = f"call_{call_number:02d}_{scenario_name}"
        filename = f"{base_name}.json"
        filepath = self.runs_dir / "transcripts" / filename
        
        # Download recording with matching name
        recording_url = call_details.get("recordingUrl", "")
        recording_path = self.download_recording(call_id, recording_url, base_name)
        
        # Prepare comprehensive call data
        call_data = {
            "call_id": call_id,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "datetime": datetime.now().isoformat(),
            "persona": persona,
            "call_details": call_details,
            "transcript": self._extract_transcript(call_details),
            "recording_file": recording_path,
            "metadata": {
                "target_phone": "+18054398008",
                "duration": call_details.get("duration"),
                "status": call_details.get("status"),
                "cost": call_details.get("cost")
            }
        }
        
        # Save to file
        with open(filepath, 'w') as f:
            json.dump(call_data, f, indent=2, default=str)
        
        return str(filepath)
    
    def _extract_transcript(self, call_details: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract and format transcript from call details"""
        
        transcript = []
        messages = call_details.get("messages", [])
        
        for message in messages:
            # Handle different message formats from VAPI
            if isinstance(message, dict):
                role = message.get("role", "unknown")
                content = message.get("content", "")
                timestamp = message.get("timestamp", "")
                
                transcript.append({
                    "timestamp": timestamp,
                    "speaker": "patient" if role == "user" else "system",
                    "text": content
                })
        
        return transcript
    
    def analyze_call_for_bugs(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze call transcript for potential bugs"""
        
        transcript = call_data.get("transcript", [])
        persona = call_data.get("persona", {})
        expected_bugs = persona.get("expected_bugs_to_test", [])
        
        analysis = {
            "call_id": call_data.get("call_id"),
            "analysis_timestamp": datetime.now().isoformat(),
            "persona_scenario": persona.get("scenario"),
            "bugs_found": [],
            "quality_issues": [],
            "conversation_flow_issues": [],
            "information_gaps": [],
            "overall_rating": None
        }
        
        # Analyze transcript
        system_messages = [msg for msg in transcript if msg["speaker"] == "system"]
        patient_messages = [msg for msg in transcript if msg["speaker"] == "patient"]
        
        # Bug Detection Logic
        analysis["bugs_found"] = self._detect_bugs(system_messages, patient_messages, expected_bugs)
        analysis["quality_issues"] = self._detect_quality_issues(system_messages)
        analysis["conversation_flow_issues"] = self._analyze_conversation_flow(transcript)
        analysis["information_gaps"] = self._detect_information_gaps(transcript, persona)
        
        # Overall rating
        total_issues = len(analysis["bugs_found"]) + len(analysis["quality_issues"])
        if total_issues == 0:
            analysis["overall_rating"] = "Good"
        elif total_issues <= 2:
            analysis["overall_rating"] = "Fair"
        else:
            analysis["overall_rating"] = "Poor"
        
        return analysis
    
    def _detect_bugs(self, system_messages: List[Dict], patient_messages: List[Dict], 
                    expected_bugs: List[str]) -> List[Dict[str, Any]]:
        """Detect specific bugs in system responses"""
        
        bugs_found = []
        
        for message in system_messages:
            text = message.get("text", "").lower()
            
            # Check for hallucinated information
            if any(phrase in text for phrase in [
                "i'm not sure", "i don't have that information", 
                "let me check", "i'll transfer you"
            ]) and len([m for m in system_messages if "transfer" in m.get("text", "")]) == 0:
                bugs_found.append({
                    "type": "Potential Hallucination",
                    "description": "System claims uncertainty but doesn't offer proper escalation",
                    "message": message.get("text"),
                    "timestamp": message.get("timestamp")
                })
            
            # Check for awkward phrasing
            if any(phrase in text for phrase in [
                "um", "uh", "like", "you know", "sort of", "kind of"
            ]):
                bugs_found.append({
                    "type": "Awkward Phrasing",
                    "description": "Unprofessional speech patterns detected",
                    "message": message.get("text"),
                    "timestamp": message.get("timestamp")
                })
            
            # Check for inappropriate responses
            if any(phrase in text for phrase in [
                "i can't help", "that's not my job", "call someone else"
            ]):
                bugs_found.append({
                    "type": "Inappropriate Response",
                    "description": "Unhelpful or dismissive response to patient",
                    "message": message.get("text"),
                    "timestamp": message.get("timestamp")
                })
        
        return bugs_found
    
    def _detect_quality_issues(self, system_messages: List[Dict]) -> List[Dict[str, Any]]:
        """Detect conversation quality issues"""
        
        quality_issues = []
        
        # Check for repetitive responses
        message_texts = [msg.get("text", "") for msg in system_messages]
        for i, text in enumerate(message_texts):
            if message_texts.count(text) > 2:
                quality_issues.append({
                    "type": "Repetitive Responses",
                    "description": f"Same response repeated {message_texts.count(text)} times",
                    "message": text
                })
                break
        
        # Check for very short responses
        short_responses = [msg for msg in system_messages if len(msg.get("text", "")) < 10]
        if len(short_responses) > 3:
            quality_issues.append({
                "type": "Overly Brief Responses",
                "description": f"{len(short_responses)} responses were very short",
                "examples": [msg.get("text") for msg in short_responses[:3]]
            })
        
        return quality_issues
    
    def _analyze_conversation_flow(self, transcript: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze conversation flow issues"""
        
        flow_issues = []
        
        # Check for abrupt topic changes
        # Check if system asks for information already provided
        patient_provided_info = set()
        for i, message in enumerate(transcript):
            if message["speaker"] == "patient":
                text = message.get("text", "").lower()
                
                # Track what patient mentioned
                if "name" in text or "i'm" in text:
                    patient_provided_info.add("name")
                if "insurance" in text:
                    patient_provided_info.add("insurance")
                if "appointment" in text:
                    patient_provided_info.add("appointment")
            
            elif message["speaker"] == "system":
                text = message.get("text", "").lower()
                
                # Check if asking for already provided info
                if "name" in text and "name" in patient_provided_info:
                    flow_issues.append({
                        "type": "Redundant Information Request",
                        "description": "Asked for name after patient already provided it",
                        "timestamp": message.get("timestamp")
                    })
        
        return flow_issues
    
    def _detect_information_gaps(self, transcript: List[Dict], persona: Dict) -> List[str]:
        """Detect missing information collection"""
        
        gaps = []
        all_text = " ".join([msg.get("text", "") for msg in transcript]).lower()
        
        # Check if essential info was collected based on scenario
        scenario = persona.get("scenario", "")
        
        if scenario == "appointment_scheduling":
            if "name" not in all_text and "what's your name" not in all_text:
                gaps.append("Patient name never collected")
            if "insurance" not in all_text and "coverage" not in all_text:
                gaps.append("Insurance information never verified")
            if "birth" not in all_text and "dob" not in all_text:
                gaps.append("Date of birth never collected")
        
        elif scenario == "urgent_medication":
            if "medication" not in all_text and "prescription" not in all_text:
                gaps.append("Specific medication never identified")
            if "doctor" not in all_text and "physician" not in all_text:
                gaps.append("Prescribing doctor never identified")
            if "pharmacy" not in all_text:
                gaps.append("Pharmacy information never collected")
        
        return gaps
    
    def save_analysis(self, analysis: Dict[str, Any], call_number: int = 0,
                     scenario_name: str = "unknown") -> str:
        """Save bug analysis to file"""
        
        # Unified naming matching transcripts and recordings
        base_name = f"call_{call_number:02d}_{scenario_name}"
        filename = f"{base_name}_analysis.json"
        filepath = self.runs_dir / "analysis" / filename
        
        with open(filepath, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        return str(filepath)
    
    def generate_bug_report(self, analysis_files: List[str]) -> str:
        """Generate comprehensive bug report from multiple call analyses"""
        
        all_analyses = []
        for filepath in analysis_files:
            with open(filepath, 'r') as f:
                all_analyses.append(json.load(f))
        
        # Aggregate findings
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "total_calls_analyzed": len(all_analyses),
            "summary": {
                "total_bugs_found": sum(len(a.get("bugs_found", [])) for a in all_analyses),
                "total_quality_issues": sum(len(a.get("quality_issues", [])) for a in all_analyses),
                "scenarios_tested": list(set(a.get("persona_scenario") for a in all_analyses))
            },
            "bug_categories": {},
            "quality_trends": {},
            "recommendations": []
        }
        
        # Categorize bugs
        all_bugs = []
        for analysis in all_analyses:
            all_bugs.extend(analysis.get("bugs_found", []))
        
        bug_types = {}
        for bug in all_bugs:
            bug_type = bug.get("type", "Unknown")
            if bug_type not in bug_types:
                bug_types[bug_type] = []
            bug_types[bug_type].append(bug)
        
        report["bug_categories"] = bug_types
        
        # Generate recommendations
        if "Potential Hallucination" in bug_types:
            report["recommendations"].append(
                "System shows uncertainty but lacks proper escalation protocols"
            )
        
        if "Information Gaps" in [bug.get("type") for bug in all_bugs]:
            report["recommendations"].append(
                "Improve information collection procedures for patient intake"
            )
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"bug_report_{timestamp}.json"
        report_filepath = self.runs_dir / "reports" / report_filename
        
        with open(report_filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        return str(report_filepath)
    
    def get_previous_call_data(self, scenario: str) -> Optional[Dict[str, Any]]:
        """Get data from previous call for follow-up testing"""
        
        transcript_dir = self.runs_dir / "transcripts"
        
        # Find most recent call with matching scenario
        for filepath in sorted(transcript_dir.glob("*.json"), reverse=True):
            with open(filepath, 'r') as f:
                call_data = json.load(f)
                
            if call_data.get("persona", {}).get("scenario") == scenario:
                return call_data
        
        return None
