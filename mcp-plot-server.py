"""
几何绘图 MCP 服务器
提供 点/线/圆/矩形/三角形/五边形/六边形/单向箭头/双向箭头 等工具
所有参数带有 Annotated 中文注释，透传给 LLM
"""
import math
import os
from datetime import datetime
from typing import Annotated

from mcp.server.fastmcp import FastMCP

import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plots")
os.makedirs(OUTPUT_DIR, exist_ok=True)
server = FastMCP("geometry-plot-server", instructions="几何绘图 MCP 服务器")

# 全局跟踪当前 figure
_current_fig = None


def _fig():
    """获取当前 figure，没有则创建"""
    global _current_fig
    if _current_fig is None or not plt.fignum_exists(_current_fig.number):
        _current_fig = plt.figure()
    return _current_fig


def _ax():
    """获取当前 axes，没有则在当前 figure 上创建"""
    fig = _fig()
    if not fig.axes:
        fig.add_subplot(111)
    return fig.axes[0]


def _save_to_path(filename=None, format="svg"):
    fig = _fig()
    if filename is None:
        filename = f"geometry_{fig.number}_{datetime.now():%Y%m%d_%H%M%S_%f}"
    ext = f".{format}"
    if not filename.endswith(ext):
        filename += ext
    filepath = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(filepath, format=format, dpi=300, bbox_inches="tight")
    return filepath


# ===== 几何绘图工具 =====

@server.tool(description="创建绘图窗口（自动激活），可关闭坐标轴")
def figure(
    width: Annotated[float, "画布宽度（英寸）"] = 12.0,
    height: Annotated[float, "画布高度（英寸）"] = 8.0,
    show_axis: Annotated[bool, "是否显示坐标轴，False 则隐藏"] = True,
):
    global _current_fig
    _current_fig = plt.figure(figsize=(width, height))
    ax = _current_fig.add_subplot(111)
    if not show_axis:
        ax.axis("off")
    return f"已创建绘图窗口 ({width}x{height} 英寸)，坐标轴={'显示' if show_axis else '隐藏'}"


@server.tool(description="设置坐标轴范围")
def axis_limits(
    xmin: Annotated[float, "X 轴最小值"] = 0.0,
    xmax: Annotated[float, "X 轴最大值"] = 10.0,
    ymin: Annotated[float, "Y 轴最小值"] = 0.0,
    ymax: Annotated[float, "Y 轴最大值"] = 10.0,
):
    ax = _ax()
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)


@server.tool(description="设置等比例坐标轴（确保圆是正圆、正方形不变形）")
def axis_equal():
    _ax().set_aspect("equal")


@server.tool(description="设置图像标题")
def title(
    text: Annotated[str, "标题文本"] = "",
    fontsize: Annotated[int, "字号大小"] = 18,
):
    _ax().set_title(text, fontsize=fontsize)


@server.tool(description="绘制一个点")
def point(
    x: Annotated[float, "点 X 坐标"] = 0.0,
    y: Annotated[float, "点 Y 坐标"] = 0.0,
    size: Annotated[float, "点的大小（面积）"] = 60.0,
    color: Annotated[str, "颜色，十六进制或名称，如 #E53935"] = "#E53935",
    marker: Annotated[str, "标记样式：o圆点 s方块 ^三角 *星号"] = "o",
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    ax = _ax()
    ax.scatter([x], [y], s=size, c=color, marker=marker, label=label or None,
               zorder=5, edgecolors="black", linewidth=0.5)
    if label:
        ax.text(x, y + size * 0.002, label, fontsize=9, ha="center", va="bottom")


@server.tool(description="绘制一条线段")
def line(
    x1: Annotated[float, "起点 X 坐标"] = 0.0,
    y1: Annotated[float, "起点 Y 坐标"] = 0.0,
    x2: Annotated[float, "终点 X 坐标"] = 1.0,
    y2: Annotated[float, "终点 Y 坐标"] = 1.0,
    color: Annotated[str, "线条颜色，十六进制或名称"] = "#1E88E5",
    linewidth: Annotated[float, "线条宽度"] = 2.5,
    style: Annotated[str, "线型：-实线 --虚线 -.点划线 :点线"] = "-",
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    _ax().plot([x1, x2], [y1, y2], color=color, linewidth=linewidth,
               linestyle=style, label=label or None, zorder=4)


@server.tool(description="绘制一个圆")
def circle(
    x: Annotated[float, "圆心 X 坐标"] = 0.0,
    y: Annotated[float, "圆心 Y 坐标"] = 0.0,
    radius: Annotated[float, "圆半径"] = 1.0,
    facecolor: Annotated[str, "填充颜色"] = "#4CAF50",
    edgecolor: Annotated[str, "边框颜色"] = "#1B5E20",
    linewidth: Annotated[float, "边框宽度"] = 2.0,
    alpha: Annotated[float, "透明度，0-1"] = 0.6,
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    ax = _ax()
    ax.add_patch(Circle((x, y), radius, facecolor=facecolor, edgecolor=edgecolor,
                         linewidth=linewidth, alpha=alpha, label=label or None, zorder=3))
    ax.plot([x], [y], "+", color=edgecolor, markersize=8, zorder=5)


@server.tool(description="绘制一个矩形（左下角x/y + 宽/高）")
def rectangle(
    x: Annotated[float, "左下角 X 坐标"] = 0.0,
    y: Annotated[float, "左下角 Y 坐标"] = 0.0,
    width: Annotated[float, "矩形宽度"] = 2.0,
    height: Annotated[float, "矩形高度"] = 1.5,
    facecolor: Annotated[str, "填充颜色"] = "#FF9800",
    edgecolor: Annotated[str, "边框颜色"] = "#E65100",
    linewidth: Annotated[float, "边框宽度"] = 2.0,
    alpha: Annotated[float, "透明度，0-1"] = 0.6,
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    _ax().add_patch(Rectangle((x, y), width, height, facecolor=facecolor,
                               edgecolor=edgecolor, linewidth=linewidth,
                               alpha=alpha, label=label or None, zorder=3))


@server.tool(description="绘制一个三角形（三个顶点）")
def triangle(
    x1: Annotated[float, "顶点1 X 坐标"] = 0.0,
    y1: Annotated[float, "顶点1 Y 坐标"] = 0.0,
    x2: Annotated[float, "顶点2 X 坐标"] = 4.0,
    y2: Annotated[float, "顶点2 Y 坐标"] = 0.0,
    x3: Annotated[float, "顶点3 X 坐标"] = 2.0,
    y3: Annotated[float, "顶点3 Y 坐标"] = 3.0,
    facecolor: Annotated[str, "填充颜色"] = "#9C27B0",
    edgecolor: Annotated[str, "边框颜色"] = "#4A148C",
    linewidth: Annotated[float, "边框宽度"] = 2.0,
    alpha: Annotated[float, "透明度，0-1"] = 0.6,
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    _ax().add_patch(Polygon([(x1, y1), (x2, y2), (x3, y3)], closed=True,
                             facecolor=facecolor, edgecolor=edgecolor,
                             linewidth=linewidth, alpha=alpha,
                             label=label or None, zorder=3))


@server.tool(description="绘制一个正五边形（中心+半径）")
def pentagon(
    center_x: Annotated[float, "中心 X 坐标"] = 0.0,
    center_y: Annotated[float, "中心 Y 坐标"] = 0.0,
    radius: Annotated[float, "外接圆半径"] = 1.0,
    facecolor: Annotated[str, "填充颜色"] = "#00BCD4",
    edgecolor: Annotated[str, "边框颜色"] = "#006064",
    linewidth: Annotated[float, "边框宽度"] = 2.0,
    alpha: Annotated[float, "透明度，0-1"] = 0.6,
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    verts = _regular_polygon_verts(center_x, center_y, radius, 5)
    _ax().add_patch(Polygon(verts, closed=True, facecolor=facecolor,
                             edgecolor=edgecolor, linewidth=linewidth,
                             alpha=alpha, label=label or None, zorder=3))


@server.tool(description="绘制一个正六边形（中心+半径）")
def hexagon(
    center_x: Annotated[float, "中心 X 坐标"] = 0.0,
    center_y: Annotated[float, "中心 Y 坐标"] = 0.0,
    radius: Annotated[float, "外接圆半径"] = 1.0,
    facecolor: Annotated[str, "填充颜色"] = "#8BC34A",
    edgecolor: Annotated[str, "边框颜色"] = "#33691E",
    linewidth: Annotated[float, "边框宽度"] = 2.0,
    alpha: Annotated[float, "透明度，0-1"] = 0.6,
    label: Annotated[str, "图例标签（空则不显示）"] = "",
):
    verts = _regular_polygon_verts(center_x, center_y, radius, 6)
    _ax().add_patch(Polygon(verts, closed=True, facecolor=facecolor,
                             edgecolor=edgecolor, linewidth=linewidth,
                             alpha=alpha, label=label or None, zorder=3))


@server.tool(description="绘制单向箭头（起点→终点）")
def arrow(
    x1: Annotated[float, "起点 X 坐标"] = 0.0,
    y1: Annotated[float, "起点 Y 坐标"] = 0.0,
    x2: Annotated[float, "终点 X 坐标"] = 2.0,
    y2: Annotated[float, "终点 Y 坐标"] = 2.0,
    color: Annotated[str, "箭头颜色"] = "#D32F2F",
    linewidth: Annotated[float, "箭杆线宽"] = 2.0,
    head_width: Annotated[float, "箭头宽度"] = 0.3,
    head_length: Annotated[float, "箭头长度"] = 0.3,
    label: Annotated[str, "图例标签"] = "",
):
    ax = _ax()
    ax.plot([x1, x2], [y1, y2], color=color, lw=linewidth, solid_capstyle="round", zorder=4)
    _draw_arrowhead(ax, x1, y1, x2, y2, color, float(head_width), float(head_length))
    if label:
        ax.plot([], [], color=color, lw=linewidth, label=label)
    return f"arrow ({x1},{y1})->({x2},{y2}) hw={head_width} hl={head_length}"


@server.tool(description="绘制双向箭头（两端都有箭头）")
def double_arrow(
    x1: Annotated[float, "起点 X 坐标"] = 0.0,
    y1: Annotated[float, "起点 Y 坐标"] = 0.0,
    x2: Annotated[float, "终点 X 坐标"] = 2.0,
    y2: Annotated[float, "终点 Y 坐标"] = 2.0,
    color: Annotated[str, "箭头颜色"] = "#D32F2F",
    linewidth: Annotated[float, "箭杆线宽"] = 2.0,
    head_width: Annotated[float, "箭头宽度"] = 0.3,
    head_length: Annotated[float, "箭头长度"] = 0.3,
    label: Annotated[str, "图例标签"] = "",
):
    ax = _ax()
    ax.plot([x1, x2], [y1, y2], color=color, lw=linewidth, solid_capstyle="round", zorder=4)
    _draw_arrowhead(ax, x1, y1, x2, y2, color, float(head_width), float(head_length))
    _draw_arrowhead(ax, x2, y2, x1, y1, color, float(head_width), float(head_length))
    if label:
        ax.plot([], [], color=color, lw=linewidth, label=label)
    return f"double_arrow ({x1},{y1})<->({x2},{y2})"


@server.tool(description="添加文本标注")
def text(
    x: Annotated[float, "文本 X 坐标"] = 0.0,
    y: Annotated[float, "文本 Y 坐标"] = 0.0,
    text_str: Annotated[str, "文本内容"] = "",
    fontsize: Annotated[int, "字号"] = 12,
    color: Annotated[str, "文本颜色"] = "black",
):
    _ax().text(x, y, text_str, fontsize=fontsize, color=color,
               ha="center", va="center", fontweight="bold")


@server.tool(description="保存图像到文件（SVG/PNG）")
def saveas(
    filename: Annotated[str, "文件名（不含扩展名，留空自动生成）"] = "",
    format: Annotated[str, "格式：svg 或 png"] = "svg",
):
    return f"已保存: {_save_to_path(filename, format)}"


@server.tool(description="关闭绘图窗口，释放内存")
def close():
    global _current_fig
    if _current_fig:
        plt.close(_current_fig)
        _current_fig = None


# ===== 内部 =====
def _draw_arrowhead(ax, x1, y1, x2, y2, color, hw, hl):
    """在 (x2,y2) 处绘制指向 (x1,y1) 方向的三角形箭头"""
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    ux, uy = dx / length, dy / length  # 箭杆方向单位向量
    vx, vy = -uy, ux                   # 垂直方向
    tip = (x2, y2)
    left = (x2 - hl * ux + hw * vx, y2 - hl * uy + hw * vy)
    right = (x2 - hl * ux - hw * vx, y2 - hl * uy - hw * vy)
    ax.add_patch(Polygon([tip, left, right], closed=True,
                         facecolor=color, edgecolor="none", zorder=5))


def _regular_polygon_verts(cx, cy, r, n):
    return [(cx + r * math.cos(2 * math.pi * i / n + math.pi / 2),
             cy + r * math.sin(2 * math.pi * i / n + math.pi / 2))
            for i in range(n)]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"[Geometry Plot MCP] http://127.0.0.1:8000/mcp")
    server.run("streamable-http")
