from typing import List, Optional, Any
from karate_graph_analyzer.models import Dependency, DependencyType, Scenario

class ApiContextTracker:
    """Tracks API context (URL, Path, Method) during feature file parsing."""

    def __init__(self, api_extractor: Any = None) -> None:
        self.api_extractor = api_extractor
        self.reset()

    def reset(self) -> None:
        """Reset the internal state for a new scenario."""
        self.current_base_url_dep: Optional[Dependency] = None
        self.current_api_paths: List[Dependency] = []
        self.has_emitted_api = False
        self.dependencies: List[Dependency] = []

    def process_dependency(self, dep: Dependency, scenario: Scenario, http_method: str) -> bool:
        """Process an API dependency and track its state.
        
        Returns:
            True if the dependency was handled by the tracker.
        """
        if dep.type != DependencyType.API:
            return False

        if dep.target == "METHOD_MARKER":
            self.emit_api_call(dep.line_number, scenario, http_method)
            # Reset paths for next call, but keep URL context
            self.current_api_paths = []
        elif dep.parameters.get("path_only"):
            self.current_api_paths.append(dep)
        else:
            self.current_base_url_dep = dep
            
        return True

    def finalize(self, line_number: int, scenario: Scenario, http_method: str) -> List[Dependency]:
        """Finalize tracking at the end of a scenario."""
        self.emit_api_call(line_number, scenario, http_method, is_final=True)
        return self.dependencies

    def emit_api_call(self, line_number: int, scenario: Scenario, http_method: str, is_final: bool = False) -> None:
        """Emit a consolidated API dependency based on current state."""
        if not self.current_base_url_dep and not self.current_api_paths:
            return

        if self.current_base_url_dep and self.current_api_paths:
            # Combine URL + all Paths
            combined_path = "".join([p.target for p in self.current_api_paths])
            full_url = f"{self.current_base_url_dep.target}{combined_path}"
            
            template = combined_path
            examples = []
            if self.api_extractor:
                template, examples = self.api_extractor.detect_dynamic_params(combined_path)
            
            self.dependencies.append(Dependency(
                type=DependencyType.API,
                target=full_url,
                line_number=line_number,
                parameters={
                    **self.current_api_paths[-1].parameters,
                    "base_url": self.current_base_url_dep.target,
                    "path": combined_path,
                    "path_template": template,
                    "examples": examples,
                    "combined": True,
                    "scenario_name": scenario.name,
                    "scenario_tags": scenario.tags,
                    "http_method": http_method
                }
            ))
            self.has_emitted_api = True
            
        elif self.current_base_url_dep:
            # URL only
            if is_final and self.has_emitted_api:
                return
                
            d = self.current_base_url_dep
            d.parameters.update({
                "scenario_name": scenario.name,
                "scenario_tags": scenario.tags,
                "http_method": http_method
            })
            self.dependencies.append(d)
            self.has_emitted_api = True
            
        elif self.current_api_paths:
            # Path only (fallback)
            for p in self.current_api_paths:
                template = p.target
                examples = []
                if self.api_extractor:
                    template, examples = self.api_extractor.detect_dynamic_params(p.target)
                    
                p.parameters.update({
                    "path_template": template,
                    "examples": examples,
                    "scenario_name": scenario.name,
                    "scenario_tags": scenario.tags,
                    "http_method": http_method
                })
                self.dependencies.append(p)
            self.has_emitted_api = True
