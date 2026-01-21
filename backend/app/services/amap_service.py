"""高德地图MCP服务封装"""

from typing import List, Dict, Any, Optional
import ast
import json
import re
from hello_agents.tools import MCPTool
from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

# 全局MCP工具实例
_amap_mcp_tool = None


def _try_parse_mcp_payload(raw: Any) -> Any:
    """尽量把 MCPTool.run 返回的内容解析为 Python 对象。

    MCP 返回可能是：
    - JSON 字符串
    - 含说明文字的 JSON 片段
    - Python dict 字符串(单引号)
    """

    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw

    text = str(raw).strip()
    if not text:
        return None

    # 1) 直接当 JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2) 从文本中截取 JSON 对象/数组
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                # 3) 尝试按 Python literal 解析(单引号等)
                try:
                    return ast.literal_eval(snippet)
                except Exception:
                    pass

    # 4) 正则抓取第一个 JSON 块(兜底)
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        snippet = m.group(1)
        try:
            return json.loads(snippet)
        except Exception:
            try:
                return ast.literal_eval(snippet)
            except Exception:
                return None

    return None


def _parse_location_str(loc: Any) -> Optional[Location]:
    if not loc:
        return None
    if isinstance(loc, dict) and "longitude" in loc and "latitude" in loc:
        try:
            return Location(longitude=float(loc["longitude"]), latitude=float(loc["latitude"]))
        except Exception:
            return None

    # AMap 常见格式: "lng,lat"
    if isinstance(loc, str) and "," in loc:
        try:
            lng_str, lat_str = loc.split(",", 1)
            return Location(longitude=float(lng_str), latitude=float(lat_str))
        except Exception:
            return None
    return None


def _dig_first(d: Any, path: list[str]) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        f = _as_float(value)
        if f is None:
            return None
        return int(round(f))
    except Exception:
        return None


def _format_distance_m(distance_m: Optional[float]) -> str:
    if distance_m is None:
        return "未知距离"
    if distance_m >= 1000:
        return f"{distance_m / 1000:.1f} 公里"
    return f"{int(round(distance_m))} 米"


def _format_duration_s(duration_s: Optional[int]) -> str:
    if duration_s is None:
        return "未知时长"
    minutes = max(1, int(round(duration_s / 60)))
    if minutes < 60:
        return f"约 {minutes} 分钟"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"约 {hours} 小时"
    return f"约 {hours} 小时 {mins} 分钟"


_COORD_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")


def _is_coord_text(text: Optional[str]) -> bool:
    if not text:
        return False
    return bool(_COORD_RE.match(str(text)))


def get_amap_mcp_tool() -> MCPTool:
    """
    获取高德地图MCP工具实例(单例模式)
    
    Returns:
        MCPTool实例
    """
    global _amap_mcp_tool
    
    if _amap_mcp_tool is None:
        settings = get_settings()
        
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        # 创建MCP工具
        _amap_mcp_tool = MCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            server_command=["uvx", "amap-mcp-server"],
            env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
            auto_expand=True  # 自动展开为独立工具
        )
        
        print(f"✅ 高德地图MCP工具初始化成功")
        print(f"   工具数量: {len(_amap_mcp_tool._available_tools)}")
        
        # 打印可用工具列表
        if _amap_mcp_tool._available_tools:
            print("   可用工具:")
            for tool in _amap_mcp_tool._available_tools[:5]:  # 只打印前5个
                print(f"     - {tool.get('name', 'unknown')}")
            if len(_amap_mcp_tool._available_tools) > 5:
                print(f"     ... 还有 {len(_amap_mcp_tool._available_tools) - 5} 个工具")
    
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装类"""
    
    def __init__(self):
        """初始化服务"""
        self.mcp_tool = get_amap_mcp_tool()
    
    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        """
        搜索POI
        
        Args:
            keywords: 搜索关键词
            city: 城市
            citylimit: 是否限制在城市范围内
            
        Returns:
            POI信息列表
        """
        try:
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_text_search",
                "arguments": {
                    "keywords": keywords,
                    "city": city,
                    "citylimit": str(citylimit).lower()
                }
            })
            
            print(f"POI搜索结果: {str(result)[:200]}...")  # 打印前200字符

            data = _try_parse_mcp_payload(result)
            if data is None:
                return []

            # AMap 通常返回 {"pois": [...]} 或 {"data": {"pois": [...]}}
            pois = None
            if isinstance(data, dict):
                if isinstance(data.get("pois"), list):
                    pois = data.get("pois")
                elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("pois"), list):
                    pois = data["data"].get("pois")
                elif isinstance(data.get("results"), list):
                    pois = data.get("results")

            if pois is None and isinstance(data, list):
                pois = data

            if not pois:
                return []

            parsed: List[POIInfo] = []
            # 为了生成行程，优先保证前若干个 POI 有坐标；缺坐标时用详情接口补齐
            max_collect = 15
            for item in pois:
                if not isinstance(item, dict):
                    continue

                poi_id = item.get("id") or item.get("poi_id") or item.get("uid") or ""
                name = item.get("name") or ""
                poi_type = item.get("type") or item.get("typecode") or ""
                address = item.get("address") or item.get("addr") or ""
                location = _parse_location_str(item.get("location") or item.get("lnglat"))

                # 有些 maps_text_search 返回不含 location，需要再调 detail 补齐
                if not location and poi_id:
                    detail = self.get_poi_detail(str(poi_id))
                    if isinstance(detail, dict):
                        # detail 往往包含 location/type/rating 等
                        location = _parse_location_str(detail.get("location"))
                        poi_type = detail.get("type") or poi_type
                        name = detail.get("name") or name
                        address = detail.get("address") or address

                if not location:
                    # 仍拿不到坐标就跳过
                    continue

                parsed.append(
                    POIInfo(
                        id=str(poi_id),
                        name=str(name),
                        type=str(poi_type),
                        address=str(address),
                        location=location,
                        tel=item.get("tel"),
                    )
                )

                if len(parsed) >= max_collect:
                    break

            return parsed
            
        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return []

    def find_first_poi_with_location(
        self,
        keywords: str,
        city: str,
        citylimit: bool = True,
        max_candidates: int = 5,
    ) -> Optional[POIInfo]:
        """更快地拿到“第一个可用 POI（带坐标）”。

        用于像“机场/火车站”等场景：我们只需要一个目的地坐标，不需要收集很多 POI，
        避免 search_poi 为补坐标触发大量详情请求。
        """

        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_text_search",
                    "arguments": {
                        "keywords": keywords,
                        "city": city,
                        "citylimit": str(citylimit).lower(),
                    },
                }
            )

            data = _try_parse_mcp_payload(result)
            if data is None:
                return None

            pois: Optional[list] = None
            if isinstance(data, dict) and isinstance(data.get("pois"), list):
                pois = data.get("pois")
            elif isinstance(data, dict) and isinstance(data.get("data"), dict) and isinstance(data["data"].get("pois"), list):
                pois = data["data"].get("pois")
            elif isinstance(data, list):
                pois = data

            if not pois:
                return None

            checked = 0
            for item in pois:
                if not isinstance(item, dict):
                    continue
                checked += 1
                if checked > max_candidates:
                    break

                poi_id = item.get("id") or item.get("poi_id") or item.get("uid") or ""
                name = item.get("name") or ""
                poi_type = item.get("type") or item.get("typecode") or ""
                address = item.get("address") or item.get("addr") or ""
                location = _parse_location_str(item.get("location") or item.get("lnglat"))

                if not location and poi_id:
                    detail = self.get_poi_detail(str(poi_id))
                    if isinstance(detail, dict):
                        location = _parse_location_str(detail.get("location"))
                        poi_type = detail.get("type") or poi_type
                        name = detail.get("name") or name
                        address = detail.get("address") or address

                if not location:
                    continue

                return POIInfo(
                    id=str(poi_id),
                    name=str(name),
                    type=str(poi_type),
                    address=str(address),
                    location=location,
                    tel=item.get("tel"),
                )

            return None

        except Exception as e:
            print(f"❌ POI快速搜索失败: {str(e)}")
            return None
    
    def get_weather(self, city: str) -> List[WeatherInfo]:
        """
        查询天气
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息列表
        """
        try:
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_weather",
                "arguments": {
                    "city": city
                }
            })
            
            print(f"天气查询结果: {result[:200]}...")
            
            # TODO: 解析实际的天气数据
            return []
            
        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return []
    
    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Dict[str, Any]:
        """
        规划路线
        
        Args:
            origin_address: 起点地址
            destination_address: 终点地址
            origin_city: 起点城市
            destination_city: 终点城市
            route_type: 路线类型 (walking/driving/transit)
            
        Returns:
            路线信息
        """
        try:
            use_coordinates = _is_coord_text(origin_address) and _is_coord_text(destination_address)

            # 根据路线类型选择工具
            tool_map_addr = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address",
            }
            tool_map_coord = {
                "walking": "maps_direction_walking_by_coordinates",
                "driving": "maps_direction_driving_by_coordinates",
                "transit": "maps_direction_transit_integrated_by_coordinates",
            }

            tool_name = (
                tool_map_coord.get(route_type, "maps_direction_walking_by_coordinates")
                if use_coordinates
                else tool_map_addr.get(route_type, "maps_direction_walking_by_address")
            )

            # 构建参数
            if use_coordinates:
                arguments = {"origin": origin_address, "destination": destination_address}
            else:
                arguments = {"origin_address": origin_address, "destination_address": destination_address}

                # 公共交通需要城市参数
                if route_type == "transit":
                    if origin_city:
                        arguments["origin_city"] = origin_city
                    if destination_city:
                        arguments["destination_city"] = destination_city
                else:
                    # 其他路线类型也可以提供城市参数提高准确性
                    if origin_city:
                        arguments["origin_city"] = origin_city
                    if destination_city:
                        arguments["destination_city"] = destination_city
            
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": tool_name,
                "arguments": arguments
            })

            print(f"路线规划结果: {str(result)[:200]}...")

            data = _try_parse_mcp_payload(result)
            if data is None:
                return {"raw": result}

            # 兼容 AMap 常见结构
            # driving/walking: route.paths[0].distance/duration/steps[].instruction
            # transit: route.transits[0].distance/duration/segments
            route = None
            if isinstance(data, dict):
                route = data.get("route")
                if route is None and isinstance(data.get("data"), dict):
                    route = data["data"].get("route")
                if route is None and isinstance(data.get("result"), dict):
                    route = data["result"].get("route")

            distance_m: Optional[float] = None
            duration_s: Optional[int] = None
            instructions: list[str] = []

            if isinstance(route, dict):
                # driving/walking
                paths = route.get("paths")
                if isinstance(paths, list) and paths:
                    first = paths[0] if isinstance(paths[0], dict) else None
                    if isinstance(first, dict):
                        distance_m = _as_float(first.get("distance"))
                        duration_s = _as_int(first.get("duration"))
                        steps = first.get("steps")
                        if isinstance(steps, list):
                            for step in steps:
                                if isinstance(step, dict) and step.get("instruction"):
                                    instructions.append(str(step["instruction"]))
                                    if len(instructions) >= 4:
                                        break

                # transit
                if distance_m is None and duration_s is None:
                    transits = route.get("transits")
                    if isinstance(transits, list) and transits:
                        first_t = transits[0] if isinstance(transits[0], dict) else None
                        if isinstance(first_t, dict):
                            distance_m = _as_float(first_t.get("distance"))
                            duration_s = _as_int(first_t.get("duration"))

            # 兜底：有些 MCP 会把 distance/duration 顶层返回
            if distance_m is None and isinstance(data, dict):
                distance_m = _as_float(data.get("distance") or _dig_first(data, ["data", "distance"]))
            if duration_s is None and isinstance(data, dict):
                duration_s = _as_int(data.get("duration") or _dig_first(data, ["data", "duration"]))

            summary = f"距离{_format_distance_m(distance_m)}，{_format_duration_s(duration_s)}"
            if instructions:
                summary += "；导航摘要：" + " / ".join(instructions)

            return {
                "route_type": route_type,
                "distance_m": distance_m,
                "duration_s": duration_s,
                "instructions": instructions,
                "summary": summary,
                "raw": data,
            }
            
        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return {}
    
    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码(地址转坐标)

        Args:
            address: 地址
            city: 城市

        Returns:
            经纬度坐标
        """
        try:
            arguments = {"address": address}
            if city:
                arguments["city"] = city

            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_geo",
                "arguments": arguments
            })

            print(f"地理编码结果: {result[:200]}...")

            # TODO: 解析实际的坐标数据
            return None

        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        """
        获取POI详情

        Args:
            poi_id: POI ID

        Returns:
            POI详情信息
        """
        try:
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_search_detail",
                "arguments": {
                    "id": poi_id
                }
            })

            print(f"POI详情结果: {result[:200]}...")

            # 解析结果并提取图片
            import json
            import re

            # 尝试从结果中提取JSON
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data

            return {"raw": result}

        except Exception as e:
            print(f"❌ 获取POI详情失败: {str(e)}")
            return {}


# 创建全局服务实例
_amap_service = None


def get_amap_service() -> AmapService:
    """获取高德地图服务实例(单例模式)"""
    global _amap_service
    
    if _amap_service is None:
        _amap_service = AmapService()
    
    return _amap_service

