import asyncio
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add src directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vapi_client import VAPIClient
from assistant_factory import AssistantFactory
from storage import CallStorage

class CallRunner:
    """Main orchestrator for running test calls and analyzing results"""
    
    def __init__(self):
        self.vapi = VAPIClient()
        self.storage = CallStorage()
        self.target_phone = os.getenv('TARGET_PHONE_NUMBER', '+18054398008')
        self.call_counter = 0
        
    async def run_single_call(self, persona_type: str = "random", 
                            follow_up_scenario: Optional[str] = None,
                            call_number: Optional[int] = None) -> Dict[str, Any]:
        """Run a single test call with specified persona"""
        
        print(f"🎬 Starting call with persona: {persona_type}")
        
        # Get persona
        if follow_up_scenario:
            # Get previous call data for follow-up
            previous_data = self.storage.get_previous_call_data(follow_up_scenario)
            if previous_data:
                persona = AssistantFactory.get_follow_up_caller_persona(previous_data)
            else:
                print(f"⚠️  No previous {follow_up_scenario} call found, using regular persona")
                persona = AssistantFactory.get_appointment_scheduler_persona()
        elif persona_type == "random":
            persona = AssistantFactory.get_random_persona()
        else:
            # Get specific persona
            persona_map = {
                "appointment": AssistantFactory.get_appointment_scheduler_persona,
                "elderly": AssistantFactory.get_confused_elderly_persona,
                "urgent": AssistantFactory.get_urgent_medication_persona,
                "insurance": AssistantFactory.get_insurance_questioner_persona
            }
            persona_func = persona_map.get(persona_type)
            if persona_func:
                persona = persona_func()
            else:
                print(f"⚠️  Unknown persona type: {persona_type}, using random")
                persona = AssistantFactory.get_random_persona()
        
        # Determine call number
        if call_number is None:
            self.call_counter += 1
            call_number = self.call_counter
        
        print(f"📋 Persona: {persona['name']}")
        print(f"🎯 Testing for: {', '.join(persona['expected_bugs_to_test'])}")
        
        try:
            # Step 1: Create assistant
            print("🤖 Creating VAPI assistant...")
            assistant_response = await self.vapi.create_assistant(
                name=persona["name"],
                system_prompt=persona["system_prompt"],
                voice_settings=persona["voice_settings"]
            )
            
            assistant_id = assistant_response["id"]
            print(f"✅ Assistant created: {assistant_id}")
            
            # Step 2: Make call
            print(f"📞 Making call to {self.target_phone}...")
            call_response = await self.vapi.make_outbound_call(
                assistant_id=assistant_id,
                phone_number=self.target_phone,
                metadata={
                    "test_scenario": persona["scenario"],
                    "test_timestamp": datetime.now().isoformat(),
                    "expected_bugs": persona["expected_bugs_to_test"]
                }
            )
            
            call_id = call_response["id"]
            print(f"☎️  Call initiated: {call_id}")
            
            # Step 3: Wait for completion
            print("⏳ Waiting for call to complete...")
            call_details = await self.vapi.wait_for_call_completion(call_id, timeout=600)
            
            print(f"✅ Call completed with status: {call_details.get('status')}")
            print(f"⏱️  Duration: {call_details.get('duration', 'unknown')} seconds")
            
            # Step 4: Save call data
            print("💾 Saving call data...")
            scenario_name = persona.get('scenario', 'unknown')
            call_filepath = self.storage.save_call_data(call_id, call_details, persona, call_number, scenario_name)
            print(f"💾 Call data saved: {call_filepath}")
            
            # Step 5: Log cost
            self.storage.log_cost(call_id, call_details, call_number, scenario_name)

            # Step 6: Analyze for bugs
            print("🔍 Analyzing call for bugs...")
            call_data = {
                "call_id": call_id,
                "persona": persona,
                "call_details": call_details,
                "transcript": self.storage._extract_transcript(call_details)
            }
            
            analysis = self.storage.analyze_call_for_bugs(call_data)
            analysis_filepath = self.storage.save_analysis(analysis, call_number, scenario_name)
            
            # Step 6: Print results
            self._print_call_results(analysis)
            
            # Step 7: Cleanup assistant
            print("🧹 Cleaning up assistant...")
            await self.vapi.delete_assistant(assistant_id)
            
            return {
                "success": True,
                "call_id": call_id,
                "call_filepath": call_filepath,
                "analysis_filepath": analysis_filepath,
                "analysis": analysis
            }
            
        except Exception as e:
            print(f"❌ Error during call: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "persona": persona.get("name", "Unknown")
            }
    
    def _print_call_results(self, analysis: Dict[str, Any]):
        """Print formatted analysis results"""
        
        print("\n" + "="*60)
        print(f"📊 CALL ANALYSIS RESULTS")
        print("="*60)
        
        print(f"🎭 Scenario: {analysis.get('persona_scenario')}")
        print(f"⭐ Overall Rating: {analysis.get('overall_rating')}")
        
        bugs_found = analysis.get('bugs_found', [])
        if bugs_found:
            print(f"\n🐛 BUGS FOUND ({len(bugs_found)}):")
            for i, bug in enumerate(bugs_found, 1):
                print(f"  {i}. {bug.get('type')}: {bug.get('description')}")
                print(f"     Message: \"{bug.get('message', '')[:100]}...\"")
        else:
            print("\n✅ No bugs detected")
        
        quality_issues = analysis.get('quality_issues', [])
        if quality_issues:
            print(f"\n⚠️  QUALITY ISSUES ({len(quality_issues)}):")
            for i, issue in enumerate(quality_issues, 1):
                print(f"  {i}. {issue.get('type')}: {issue.get('description')}")
        
        conversation_issues = analysis.get('conversation_flow_issues', [])
        if conversation_issues:
            print(f"\n💬 CONVERSATION FLOW ISSUES ({len(conversation_issues)}):")
            for i, issue in enumerate(conversation_issues, 1):
                print(f"  {i}. {issue.get('type')}: {issue.get('description')}")
        
        info_gaps = analysis.get('information_gaps', [])
        if info_gaps:
            print(f"\n📋 INFORMATION GAPS ({len(info_gaps)}):")
            for i, gap in enumerate(info_gaps, 1):
                print(f"  {i}. {gap}")
        
        print("="*60 + "\n")
    
    async def run_test_sequence(self, num_calls: int = 5) -> List[str]:
        """Run a comprehensive test sequence with chained scenarios"""
        
        print(f"🚀 Starting comprehensive test sequence")
        print("="*60)
        
        analysis_files = []
        call_num = 0
        
        # Phase 1: Run chained scenarios (multi-step conversations)
        chains = AssistantFactory.get_chained_scenarios()
        
        for chain_idx, chain in enumerate(chains):
            chain_name = chain[0].get("chain_id", f"chain_{chain_idx}")
            print(f"\n🔗 CHAIN: {chain_name} ({len(chain)} calls)")
            print("-"*40)
            
            for step in chain:
                call_num += 1
                step_num = step.get("chain_step", "?")
                print(f"\n📞 Call {call_num} | Chain Step {step_num}: {step['name']}")
                
                result = await self._run_call_with_persona(step, call_num)
                
                if result["success"]:
                    analysis_files.append(result["analysis_filepath"])
                
                # Shorter wait between chain steps (same patient calling back)
                print("⏳ Waiting 20 seconds before next call...")
                await asyncio.sleep(20)
            
            # Longer wait between different chains
            if chain_idx < len(chains) - 1:
                print("\n⏳ Waiting 30 seconds before next chain...")
                await asyncio.sleep(30)
        
        # Phase 2: Run standalone scenarios if we need more calls (cycles through personas)
        standalone_personas = ["appointment", "elderly", "urgent", "insurance"]
        
        while call_num < num_calls:
            call_num += 1
            persona_type = standalone_personas[(call_num - 1) % len(standalone_personas)]
            print(f"\n📞 Standalone Call {call_num}: {persona_type}")
            
            result = await self.run_single_call(
                persona_type=persona_type, 
                call_number=call_num
            )
            
            if result["success"]:
                analysis_files.append(result["analysis_filepath"])
            
            if call_num < num_calls:
                print("⏳ Waiting 30 seconds before next call...")
                await asyncio.sleep(30)
        
        print(f"\n✅ Completed {call_num} calls total")
        return analysis_files
    
    async def _run_call_with_persona(self, persona: Dict[str, Any], call_number: int) -> Dict[str, Any]:
        """Run a call with a pre-built persona dict (used for chained calls)"""
        
        print(f"📋 Persona: {persona['name']}")
        print(f"🎯 Testing for: {', '.join(persona['expected_bugs_to_test'])}")
        
        try:
            # Create assistant
            print("🤖 Creating VAPI assistant...")
            assistant_response = await self.vapi.create_assistant(
                name=persona["name"],
                system_prompt=persona["system_prompt"],
                voice_settings=persona["voice_settings"]
            )
            
            assistant_id = assistant_response["id"]
            print(f"✅ Assistant created: {assistant_id}")
            
            # Make call
            print(f"📞 Making call to {self.target_phone}...")
            call_response = await self.vapi.make_outbound_call(
                assistant_id=assistant_id,
                phone_number=self.target_phone,
                metadata={
                    "test_scenario": persona["scenario"],
                    "chain_id": persona.get("chain_id", "standalone"),
                    "chain_step": persona.get("chain_step", 0),
                    "test_timestamp": datetime.now().isoformat()
                }
            )
            
            call_id = call_response["id"]
            print(f"☎️  Call initiated: {call_id}")
            
            # Wait for completion
            print("⏳ Waiting for call to complete...")
            call_details = await self.vapi.wait_for_call_completion(call_id, timeout=600)
            
            print(f"✅ Call completed with status: {call_details.get('status')}")
            
            # Save data
            scenario_name = persona.get('scenario', 'unknown')
            call_filepath = self.storage.save_call_data(call_id, call_details, persona, call_number, scenario_name)
            print(f"💾 Call data saved: {call_filepath}")
            
            # Log cost
            self.storage.log_cost(call_id, call_details, call_number, scenario_name)

            # Analyze
            call_data = {
                "call_id": call_id,
                "persona": persona,
                "call_details": call_details,
                "transcript": self.storage._extract_transcript(call_details)
            }
            analysis = self.storage.analyze_call_for_bugs(call_data)
            analysis_filepath = self.storage.save_analysis(analysis, call_number, scenario_name)
            
            self._print_call_results(analysis)
            
            # Cleanup
            await self.vapi.delete_assistant(assistant_id)
            
            return {
                "success": True,
                "call_id": call_id,
                "call_filepath": call_filepath,
                "analysis_filepath": analysis_filepath,
                "analysis": analysis
            }
            
        except Exception as e:
            print(f"❌ Error during call: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def generate_final_report(self, analysis_files: List[str]) -> str:
        """Generate final bug report from all calls"""
        
        print("\n📋 Generating final bug report...")
        
        report_filepath = self.storage.generate_bug_report(analysis_files)
        
        print(f"📄 Bug report generated: {report_filepath}")
        
        return report_filepath

async def main():
    """Main function for running the test"""
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "single":
            # Run single call
            persona_type = sys.argv[2] if len(sys.argv) > 2 else "random"
            runner = CallRunner()
            await runner.run_single_call(persona_type=persona_type)
            
        elif command == "sequence":
            # Run test sequence
            num_calls = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            runner = CallRunner()
            analysis_files = await runner.run_test_sequence(num_calls=num_calls)
            await runner.generate_final_report(analysis_files)
            
        elif command == "followup":
            # Test follow-up call
            scenario = sys.argv[2] if len(sys.argv) > 2 else "appointment_scheduling"
            runner = CallRunner()
            await runner.run_single_call(follow_up_scenario=scenario)
            
    else:
        print("🤖 Pretty Good AI Voice Bot Tester")
        print("\nUsage:")
        print("  python run_one_call.py single [persona]     # Run single call")
        print("  python run_one_call.py sequence [num]       # Run test sequence")
        print("  python run_one_call.py followup [scenario]  # Test follow-up call")
        print("\nPersona types: appointment, elderly, urgent, insurance, random")
        print("Scenarios: appointment_scheduling, confused_elderly, urgent_medication")

if __name__ == "__main__":
    asyncio.run(main())
