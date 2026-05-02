
    def calculate_weekday_metrics(trade_list):
        weekday_dict = collections.defaultdict(list)
        # 0=Monday, 6=Sunday
        for t in trade_list:
            wd = t.close_date.weekday()
            weekday_dict[wd].append(t)
        
        results = []
        # Days names mapping
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for wd, trades in weekday_dict.items():
            count = len(trades)
            wins = [t for t in trades if t.net_pl > 0]
            win_rate = (len(wins) / count * 100) if count > 0 else 0
            total_pl = sum(t.net_pl for t in trades)
            avg_pl = total_pl / count if count > 0 else 0
            
            results.append({
                'day_name': days[wd],
                'day_index': wd,
                'count': count,
                'win_rate': win_rate,
                'total_pl': total_pl,
                'avg_pl': avg_pl
            })
            
        # Sort by day index (Monday first)
        results.sort(key=lambda x: x['day_index'])
        return results
