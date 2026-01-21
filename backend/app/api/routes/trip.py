"""旅行规划API路由"""

import asyncio
import os
from fastapi import APIRouter, HTTPException
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse,
    TripPlan,
    DayPlan,
    Attraction,
    Location,
    Meal,
)
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...services.amap_service import get_amap_service

router = APIRouter(prefix="/trip", tags=["旅行规划"])


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        departure_note = _build_departure_to_airport_note(request)

        # 获取多智能体系统实例
        print("🔄 获取多智能体系统实例...")
        planner = get_trip_planner_agent()

        # 如果未配置 LLM Key，则跳过 LLM，直接用 MCP POI 生成一个可用行程
        llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not llm_api_key:
            print("⚠️  未检测到 LLM_API_KEY/OPENAI_API_KEY，使用 MCP 生成简化行程")
            trip_plan = _build_plan_from_mcp(request)
        else:
            # 生成旅行计划（增加超时保护，避免外部工具/LLM卡住导致前端Network Error）
            print("🚀 开始生成旅行计划...")
            try:
                trip_plan = await asyncio.wait_for(
                    asyncio.to_thread(planner.plan_trip, request),
                    timeout=60,
                )
            except TimeoutError:
                print("⚠️  生成旅行计划超时，改用 MCP 生成简化行程")
                trip_plan = _build_plan_from_mcp(request)

        if departure_note and trip_plan:
            try:
                existing = (trip_plan.overall_suggestions or "").strip()
                trip_plan.overall_suggestions = (departure_note + "\n\n" + existing).strip()
            except Exception:
                pass

        print("✅ 旅行计划生成成功,准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan
        )

    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


def _build_plan_from_mcp(request: TripRequest) -> TripPlan:
    """不依赖 LLM：直接用 MCP POI 搜索结果拼一个可展示的行程。"""

    from datetime import datetime, timedelta

    amap = get_amap_service()
    keywords = request.preferences[0] if request.preferences else "景点"
    pois = amap.search_poi(keywords=keywords, city=request.city, citylimit=True)

    if not pois:
        # MCP 没拿到数据，回退到原有兜底（仍然保证可用）
        planner = get_trip_planner_agent()
        return planner._create_fallback_plan(request)

    # 每天 2-3 个 POI
    per_day = 3 if request.travel_days == 1 else 2
    idx = 0
    days: list[DayPlan] = []

    try:
        start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
    except Exception:
        start_dt = datetime.now()

    for day_index in range(request.travel_days):
        day_pois = pois[idx : idx + per_day]
        if not day_pois:
            day_pois = pois[:per_day]
        idx += per_day

        attractions = [
            Attraction(
                name=p.name,
                address=p.address,
                location=Location(longitude=p.location.longitude, latitude=p.location.latitude),
                visit_duration=120,
                description=f"来自高德地图POI搜索: {p.type}" if p.type else "来自高德地图POI搜索",
                category="景点",
                poi_id=p.id,
            )
            for p in day_pois
        ]

        meals = [
            Meal(type="breakfast", name="早餐推荐", description="根据当前位置/景点分布选择附近餐饮", estimated_cost=30),
            Meal(type="lunch", name="午餐推荐", description="根据行程中途位置选择附近餐饮", estimated_cost=50),
            Meal(type="dinner", name="晚餐推荐", description="根据当日结束点选择附近餐饮", estimated_cost=80),
        ]

        days.append(
            DayPlan(
                date=(start_dt + timedelta(days=day_index)).strftime("%Y-%m-%d"),
                day_index=day_index,
                description=f"第{day_index+1}天行程（基于高德地图POI: {keywords}）",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=attractions,
                meals=meals,
            )
        )

    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        weather_info=[],
        overall_suggestions="本行程在无/慢 LLM 情况下，直接基于高德地图 MCP 返回的 POI 结果生成，用于课堂演示与作业提交。",
        budget=None,
    )


def _build_departure_to_airport_note(request: TripRequest) -> str:
    """生成“当前位置(GPS) → 目的地城市机场”的出发交通说明。

    设计目标：
    - 必须使用 GPS（sensor_context.location）
    - 不依赖 LLM（保证课堂演示稳定）
    - 失败时也要给出可读的说明，不影响主行程
    """

    if not request.sensor_context or not request.sensor_context.location:
        return ""

    loc = request.sensor_context.location
    origin = f"{loc.longitude},{loc.latitude}"

    amap = get_amap_service()
    airport = amap.find_first_poi_with_location(keywords="机场", city=request.city, citylimit=True, max_candidates=5)
    if not airport:
        return (
            "出发交通建议（基于GPS定位）：已获取你的当前位置，但未能在目的地城市搜索到机场POI，"
            "本次行程将只按目的地城市生成。"
        )

    dest_coord = f"{airport.location.longitude},{airport.location.latitude}"
    airport_name = airport.name or f"{request.city}机场"

    # 跨城出行默认用 driving（最稳，不依赖起点城市参数）
    route = amap.plan_route(
        origin_address=origin,
        destination_address=dest_coord,
        origin_city=None,
        destination_city=request.city,
        route_type="driving",
    )

    accuracy_part = ""
    if loc.accuracy_m is not None:
        try:
            accuracy_part = f"（精度±{int(round(loc.accuracy_m))}m）"
        except Exception:
            accuracy_part = ""

    summary = ""
    if isinstance(route, dict):
        summary = str(route.get("summary") or "").strip()

    if summary:
        return (
            f"出发交通建议（基于GPS定位{accuracy_part}）：从你当前位置前往{request.city}的{airport_name}。{summary}"
        )

    return (
        f"出发交通建议（基于GPS定位{accuracy_part}）：从你当前位置前往{request.city}的{airport_name}。"
        "路线规划结果解析失败，已按目的地城市继续生成行程。"
    )


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        # 检查多智能体系统是否可用
        planner = get_trip_planner_agent()

        return {
            "status": "healthy",
            "service": "trip-planner",
            "planner_agent_name": getattr(planner.planner_agent, "name", "") if getattr(planner, "planner_agent", None) else "",
            "sub_agents": {
                "attraction_tools": len(planner.attraction_agent.list_tools()) if getattr(planner, "attraction_agent", None) else 0,
                "weather_tools": len(planner.weather_agent.list_tools()) if getattr(planner, "weather_agent", None) else 0,
                "hotel_tools": len(planner.hotel_agent.list_tools()) if getattr(planner, "hotel_agent", None) else 0,
            },
            "has_shared_amap_tool": bool(getattr(planner, "amap_tool", None)),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )

