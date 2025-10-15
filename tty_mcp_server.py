#!/usr/bin/env python3
import sys
import json
import uuid
import time
import logging
import psutil
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tty-server")

class SessionStatus(Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"

@dataclass
class SessionStats:
    lines_written: int = 0
    bytes_written: int = 0
    commands_executed: int = 0
    last_activity: float = 0
    created_at: float = 0

@dataclass
class TTYSession:
    session_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    stats: SessionStats = None
    buffer: str = ""
    description: str = ""
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = SessionStats(created_at=time.time())

class TTYManager:
    def __init__(self):
        self.sessions: Dict[str, TTYSession] = {}
        
    def create_session(self, description: str = "") -> Dict[str, Any]:
        """创建新的 TTY 会话"""
        try:
            session_id = str(uuid.uuid4())[:8]
            session = TTYSession(
                session_id=session_id,
                description=description or f"Session-{session_id}"
            )
            self.sessions[session_id] = session
            logger.info(f"Created TTY session: {session_id}")
            
            return {
                "success": True,
                "session_id": session_id,
                "description": description,
                "message": "TTY session created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_command(self, session_id: str, command: str) -> Dict[str, Any]:
        """执行命令并稳健读取输出"""
        if session_id not in self.sessions:
            return {"success": False, "error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        
        try:
            # 执行命令
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            # 更新统计
            session.stats.commands_executed += 1
            session.stats.last_activity = time.time()
            
            # 构建输出
            output_lines = [
                f"Command: {command}",
                f"Return code: {result.returncode}",
                f"Timestamp: {time.ctime()}"
            ]
            
            if result.stdout:
                output_lines.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output_lines.append(f"STDERR:\n{result.stderr}")
                
            output = "\n".join(output_lines)
            session.buffer = output
            session.stats.bytes_written = len(output)
            session.stats.lines_written = output.count('\n') + 1
            
            return {
                "success": True,
                "session_id": session_id,
                "command": command,
                "output": output,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话统计信息（字节/行数）"""
        if session_id not in self.sessions:
            return {"error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        stats = session.stats
        
        return {
            "session_id": session_id,
            "description": session.description,
            "status": session.status.value,
            "stats": {
                "lines_written": stats.lines_written,
                "bytes_written": stats.bytes_written,
                "commands_executed": stats.commands_executed,
                "uptime_seconds": time.time() - stats.created_at,
                "last_activity_seconds": time.time() - stats.last_activity
            }
        }
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """获取单个会话详情"""
        return self.get_session_stats(session_id)
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        return [self.get_session_stats(sid) for sid in self.sessions.keys()]
    
    def terminate_session(self, session_id: str) -> Dict[str, Any]:
        """终止单个会话"""
        if session_id not in self.sessions:
            return {"success": False, "error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        session.status = SessionStatus.TERMINATED
        del self.sessions[session_id]
        
        logger.info(f"Terminated session: {session_id}")
        return {"success": True, "session_id": session_id}
    
    def batch_terminate(self, session_ids: List[str] = None) -> Dict[str, Any]:
        """批量终止会话"""
        if session_ids is None:
            session_ids = list(self.sessions.keys())
        
        results = {}
        for session_id in session_ids:
            results[session_id] = self.terminate_session(session_id)
        
        return {
            "success": True,
            "terminated_count": len([r for r in results.values() if r.get("success")]),
            "details": results
        }
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """汇总统计"""
        sessions = self.list_sessions()
        total_commands = sum(s["stats"]["commands_executed"] for s in sessions)
        total_bytes = sum(s["stats"]["bytes_written"] for s in sessions)
        total_lines = sum(s["stats"]["lines_written"] for s in sessions)
        
        return {
            "total_sessions": len(sessions),
            "active_sessions": len(sessions),
            "total_commands": total_commands,
            "total_bytes": total_bytes,
            "total_lines": total_lines,
            "session_details": sessions
        }
    
    def read_all_sessions(self) -> Dict[str, Any]:
        """一次性读取所有会话内容"""
        results = {}
        for session_id, session in self.sessions.items():
            results[session_id] = {
                "description": session.description,
                "content": session.buffer,
                "lines": session.stats.lines_written,
                "bytes": session.stats.bytes_written
            }
        return results
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        sessions = self.list_sessions()
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "active_sessions": len(sessions),
            "system_load": psutil.getloadavg(),
            "memory_usage": f"{psutil.virtual_memory().percent}%",
            "disk_usage": f"{psutil.disk_usage('/').percent}%"
        }
    
    def create_browser_session(self, url: str = None) -> Dict[str, Any]:
        """创建浏览器会话"""
        try:
            result = self.create_session(f"Browser-{uuid.uuid4()[:8]}")
            if not result["success"]:
                return result
            
            session_id = result["session_id"]
            
            # 尝试使用 lynx 文本浏览器
            if url:
                self.execute_command(session_id, f"lynx {url}")
            
            return {
                "success": True,
                "session_id": session_id,
                "type": "browser",
                "url": url,
                "message": f"Browser session created for {url}" if url else "Browser session created"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create browser session: {e}"}

# 创建管理器
tty_manager = TTYManager()

# 完整的 MCP 服务器实现
def run_mcp_server():
    """完整的 MCP 服务器实现"""
    print("🚀 Starting TTY MCP Server (Complete MCP Protocol)...", file=sys.stderr)
    
    try:
        while True:
            # 读取输入
            line = sys.stdin.readline()
            if not line:
                break
                
            try:
                request = json.loads(line.strip())
                method = request.get("method")
                params = request.get("params", {})
                id = request.get("id")
                
                # 处理 MCP 协议请求
                if method == "initialize":
                    # 初始化响应
                    response = {
                        "jsonrpc": "2.0",
                        "id": id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "tools": {}
                            },
                            "serverInfo": {
                                "name": "tty-manager",
                                "version": "1.0.0"
                            }
                        }
                    }
                    
                elif method == "tools/list":
                    # 列出所有工具
                    tools = [
                        {
                            "name": "create_session",
                            "description": "Create new TTY session",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "execute_command", 
                            "description": "Execute command with robust output reading",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {"type": "string"},
                                    "command": {"type": "string"}
                                },
                                "required": ["session_id", "command"]
                            }
                        },
                        {
                            "name": "get_session_stats",
                            "description": "Get session statistics (bytes, lines, commands)",
                            "inputSchema": {
                                "type": "object", 
                                "properties": {
                                    "session_id": {"type": "string"}
                                },
                                "required": ["session_id"]
                            }
                        },
                        {
                            "name": "get_session",
                            "description": "Get detailed session information",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {"type": "string"}
                                },
                                "required": ["session_id"]
                            }
                        },
                        {
                            "name": "list_sessions",
                            "description": "List all active sessions", 
                            "inputSchema": {"type": "object", "properties": {}}
                        },
                        {
                            "name": "terminate_session",
                            "description": "Terminate a session",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_id": {"type": "string"}
                                },
                                "required": ["session_id"]
                            }
                        },
                        {
                            "name": "batch_terminate",
                            "description": "Batch terminate multiple sessions",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "session_ids": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            }
                        },
                        {
                            "name": "get_summary",
                            "description": "Get comprehensive summary statistics",
                            "inputSchema": {"type": "object", "properties": {}}
                        },
                        {
                            "name": "read_all_sessions",
                            "description": "Read content from all sessions at once",
                            "inputSchema": {"type": "object", "properties": {}}
                        },
                        {
                            "name": "create_browser",
                            "description": "Create browser session",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "health_check",
                            "description": "Comprehensive health check",
                            "inputSchema": {"type": "object", "properties": {}}
                        }
                    ]
                    
                    response = {
                        "jsonrpc": "2.0",
                        "id": id,
                        "result": {"tools": tools}
                    }
                    
                elif method == "tools/call":
                    # 调用工具
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})
                    
                    if tool_name == "create_session":
                        result = tty_manager.create_session(arguments.get("description", ""))
                    elif tool_name == "execute_command":
                        result = tty_manager.execute_command(arguments["session_id"], arguments["command"])
                    elif tool_name == "get_session_stats":
                        result = tty_manager.get_session_stats(arguments["session_id"])
                    elif tool_name == "get_session":
                        result = tty_manager.get_session(arguments["session_id"])
                    elif tool_name == "list_sessions":
                        result = tty_manager.list_sessions()
                    elif tool_name == "terminate_session":
                        result = tty_manager.terminate_session(arguments["session_id"])
                    elif tool_name == "batch_terminate":
                        result = tty_manager.batch_terminate(arguments.get("session_ids"))
                    elif tool_name == "get_summary":
                        result = tty_manager.get_summary_stats()
                    elif tool_name == "read_all_sessions":
                        result = tty_manager.read_all_sessions()
                    elif tool_name == "create_browser":
                        result = tty_manager.create_browser_session(arguments.get("url"))
                    elif tool_name == "health_check":
                        result = tty_manager.health_check()
                    else:
                        result = {"error": f"Unknown tool: {tool_name}"}
                    
                    response = {
                        "jsonrpc": "2.0", 
                        "id": id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, indent=2, default=str)
                                }
                            ]
                        }
                    }
                    
                elif method == "notifications/initialized":
                    # 初始化完成通知，无需响应
                    continue
                    
                elif method == "ping":
                    # 心跳检测
                    response = {
                        "jsonrpc": "2.0",
                        "id": id,
                        "result": {}
                    }
                    
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}
                    }
                    
                # 发送响应
                if response:  # 只有需要响应时才发送
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                
            except json.JSONDecodeError:
                continue
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": id if 'id' in locals() else None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)

if __name__ == "__main__":
    run_mcp_server()
