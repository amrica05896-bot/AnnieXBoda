from typing import List, Optional


class AgentInfo:
    """
    Stores information about a specific browser component (e.g., Chrome/122.0 or Android 14).
    """
    def __init__(
        self,
        name: str,
        version: str,
        device: Optional[str] = None,
        os_name: Optional[str] = None,
        arch_type: Optional[str] = None,
    ):
        self.name: str = name
        self.version: str = version
        self.device: Optional[str] = device
        self.os_name: Optional[str] = os_name
        self.arch_type: Optional[str] = arch_type


class UserAgent:
    """
    Combines a list of AgentInfo objects into a standard User-Agent string.
    """
    def __init__(
        self,
        user_agents: List[AgentInfo],
    ):
        self.user_agents: List[AgentInfo] = user_agents

    def __str__(self):
        # تجميع الأجزاء بذكاء لإزالة الفواصل الزائدة
        components = []
        
        for agent in self.user_agents:
            # تجميع التفاصيل اللي بين القوسين (Device, OS, Arch)
            details_list = [
                item for item in [agent.device, agent.os_name, agent.arch_type]
                if item # فقط القيم الموجودة (غير None)
            ]
            
            # تكوين النص الأساسي: Name/Version
            agent_str = f"{agent.name}/{agent.version}"
            
            # إضافة التفاصيل بين قوسين لو موجودة
            if details_list:
                details_str = "; ".join(details_list)
                agent_str += f" ({details_str})"
            
            components.append(agent_str)

        # دمج كل المكونات بمسافة واحدة (Standard Format)
        return " ".join(components)
