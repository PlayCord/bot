"""
Graph generation utilities for PlayCord bot using matplotlib.
"""

import io
from typing import List, Tuple, Optional
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for Discord bot
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure


def generate_elo_chart(
    rating_history: List[Tuple[datetime, float]],
    title: str = "Rating Over Time",
    figsize: Tuple[int, int] = (10, 6),
    dpi: int = 100
) -> io.BytesIO:
    """
    Generate a matplotlib line chart showing ELO/TrueSkill rating progression over time.
    
    Args:
        rating_history: List of (timestamp, rating_value) tuples in chronological order
        title: Chart title
        figsize: Figure size in inches (width, height)
        dpi: Dots per inch for image quality
        
    Returns:
        BytesIO buffer containing PNG image data
        
    Raises:
        ValueError: If rating_history is empty or invalid
    """
    if not rating_history:
        raise ValueError("Cannot generate chart: rating_history is empty")
    
    # Extract timestamps and ratings
    timestamps, ratings = zip(*rating_history)
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Handle single data point
    if len(ratings) == 1:
        ax.plot(timestamps, ratings, 'o', color='#5865F2', markersize=10, label='Rating')
    else:
        # Plot line chart
        ax.plot(timestamps, ratings, linewidth=2.5, color='#5865F2', marker='o', 
                markersize=6, markerfacecolor='#5865F2', markeredgewidth=1.5, 
                markeredgecolor='white', label='Rating')
    
    # Style the chart
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Rating', fontsize=12, fontweight='bold')
    
    # Add grid for better readability
    ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
    ax.set_axisbelow(True)  # Grid behind plot
    
    # Format x-axis dates
    if len(timestamps) > 1:
        date_range = (timestamps[-1] - timestamps[0]).days
        if date_range > 60:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        elif date_range > 14:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax.xaxis.set_major_locator(mdates.DayLocator())
        
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Calculate y-axis bounds with padding
    min_rating = min(ratings)
    max_rating = max(ratings)
    rating_range = max_rating - min_rating
    
    # Handle flat ratings (all same value)
    if rating_range == 0:
        padding = max_rating * 0.1 if max_rating > 0 else 10
        ax.set_ylim(min_rating - padding, max_rating + padding)
    else:
        padding = rating_range * 0.15
        ax.set_ylim(min_rating - padding, max_rating + padding)
    
    # Add value labels at key points (start, end, min, max)
    if len(ratings) > 1:
        # Start point
        ax.annotate(f'{ratings[0]:.0f}', 
                   xy=(timestamps[0], ratings[0]),
                   xytext=(5, 10), textcoords='offset points',
                   fontsize=9, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='white', 
                           edgecolor='#5865F2', alpha=0.8))
        
        # End point
        ax.annotate(f'{ratings[-1]:.0f}', 
                   xy=(timestamps[-1], ratings[-1]),
                   xytext=(5, 10), textcoords='offset points',
                   fontsize=9, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='white', 
                           edgecolor='#5865F2', alpha=0.8))
    
    # Tight layout to prevent label cutoff
    plt.tight_layout()
    
    # Save to BytesIO buffer
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    buffer.seek(0)
    
    # Clean up
    plt.close(fig)
    
    return buffer


def generate_rating_comparison_chart(
    player_data: List[Tuple[str, List[Tuple[datetime, float]]]],
    title: str = "Rating Comparison",
    figsize: Tuple[int, int] = (12, 7),
    dpi: int = 100
) -> io.BytesIO:
    """
    Generate a matplotlib chart comparing multiple players' ratings over time.
    
    Args:
        player_data: List of (player_name, rating_history) tuples
        title: Chart title
        figsize: Figure size in inches (width, height)
        dpi: Dots per inch for image quality
        
    Returns:
        BytesIO buffer containing PNG image data
        
    Raises:
        ValueError: If player_data is empty or invalid
    """
    if not player_data:
        raise ValueError("Cannot generate chart: player_data is empty")
    
    # Color palette for multiple lines
    colors = ['#5865F2', '#57F287', '#FEE75C', '#EB459E', '#ED4245', '#00D9FF']
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    
    # Plot each player's data
    for idx, (player_name, rating_history) in enumerate(player_data):
        if not rating_history:
            continue
            
        timestamps, ratings = zip(*rating_history)
        color = colors[idx % len(colors)]
        
        ax.plot(timestamps, ratings, linewidth=2.5, color=color, 
                marker='o', markersize=5, label=player_name)
    
    # Style the chart
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Rating', fontsize=12, fontweight='bold')
    
    # Add grid and legend
    ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc='best', fontsize=10, framealpha=0.9)
    
    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Tight layout
    plt.tight_layout()
    
    # Save to BytesIO buffer
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buffer.seek(0)
    
    # Clean up
    plt.close(fig)
    
    return buffer
