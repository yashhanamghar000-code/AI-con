"""Revert auto-bind in orchestrator.__init__"""
ORC_PATH = r'c:\Users\om70c\Downloads\AI_CON_Project_Clean\scripts\agents\orchestrator.py'

with open(ORC_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

target = (
    '        # Auto-bind default CutoffAgent if None and staging folder exists\n'
    '        if cutoff_agent is None:\n'
    '            try:\n'
    '                proj_root = Path(__file__).resolve().parent.parent.parent\n'
    '                staging_p = proj_root / "cutoffs" / "phase3_final_staging"\n'
    '                if staging_p.is_dir():\n'
    '                    try:\n'
    '                        from cutoff_agent import CutoffAgent\n'
    '                    except ImportError:\n'
    '                        from scripts.agents.cutoff_agent import CutoffAgent\n'
    '                    cutoff_agent = CutoffAgent(staging_p)\n'
    '            except Exception:\n'
    '                pass\n'
    '        self.cutoff_agent = cutoff_agent\n'
    '        self.college_info_agent = college_info_agent'
)

replacement = (
    '        self.cutoff_agent = cutoff_agent\n'
    '        self.college_info_agent = college_info_agent'
)

if target in content:
    content = content.replace(target, replacement, 1)
    with open(ORC_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Reverted auto-bind")
else:
    print("Could not find target")

