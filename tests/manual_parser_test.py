"""
Manual test script to verify parser functionality with sample feature file.
"""

from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
from karate_graph_analyzer.models import ParserConfig

def main():
    """Run manual parser test."""
    parser = FeatureFileParser()
    
    # Parse the sample feature file
    ast = parser.parse_file("tests/fixtures/sample.feature")
    
    print("=" * 80)
    print("FEATURE FILE PARSING RESULTS")
    print("=" * 80)
    print(f"\nFeature Name: {ast.feature_name}")
    print(f"Background Steps: {len(ast.background_steps)}")
    print(f"Total Scenarios: {len(ast.scenarios)}")
    
    print("\n" + "-" * 80)
    print("BACKGROUND STEPS:")
    print("-" * 80)
    for step in ast.background_steps:
        print(f"  Line {step.line_number}: {step.keyword} {step.text}")
    
    print("\n" + "-" * 80)
    print("SCENARIOS:")
    print("-" * 80)
    
    for i, scenario in enumerate(ast.scenarios, 1):
        print(f"\n{i}. {scenario.name}")
        print(f"   Type: {scenario.type.value}")
        print(f"   Line: {scenario.line_number}")
        print(f"   Tags: {', '.join(scenario.tags) if scenario.tags else 'None'}")
        print(f"   Jira Tags: {', '.join(scenario.jira_tags) if scenario.jira_tags else 'None'}")
        print(f"   Steps: {len(scenario.steps)}")
        
        if scenario.examples:
            print(f"   Examples:")
            print(f"     Headers: {scenario.examples.headers}")
            print(f"     Rows: {len(scenario.examples.rows)}")
        
        # Extract dependencies
        dependencies = parser.extract_dependencies(scenario)
        if dependencies:
            print(f"   Dependencies:")
            for dep in dependencies:
                print(f"     - {dep.type.value}: {dep.target} (line {dep.line_number})")
    
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    
    total_steps = sum(len(s.steps) for s in ast.scenarios)
    total_tags = sum(len(s.tags) for s in ast.scenarios)
    total_jira_tags = sum(len(s.jira_tags) for s in ast.scenarios)
    
    print(f"Total Steps: {total_steps}")
    print(f"Total Tags: {total_tags}")
    print(f"Total Jira Tags: {total_jira_tags}")
    
    # Count dependencies by type
    from collections import Counter
    all_deps = []
    for scenario in ast.scenarios:
        all_deps.extend(parser.extract_dependencies(scenario))
    
    dep_counts = Counter(dep.type.value for dep in all_deps)
    print(f"\nDependencies by Type:")
    for dep_type, count in dep_counts.items():
        print(f"  {dep_type}: {count}")
    
    print("\n" + "=" * 80)
    print("✓ Parser test completed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    main()
