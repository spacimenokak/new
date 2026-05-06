class RatingService:
    
    @staticmethod
    def calculate_primary_score(profile):
        """Первичный рейтинг: полнота анкеты"""
        score = 0.0
        # Заполненные поля
        if profile.name: score += 0.2
        if profile.age: score += 0.2
        if profile.city: score += 0.2
        if profile.bio and len(profile.bio) > 20: score += 0.2
        return score
    
    @staticmethod
    def calculate_behavioral_score(rating):
        """Поведенческий рейтинг: лайки/скипы"""
        total = rating.total_likes + rating.total_skips
        if total == 0:
            return 0.5  # нейтральный для новых
        likes_ratio = rating.total_likes / total
        return likes_ratio
    
    @staticmethod
    def calculate_combined(primary, behavioral):
        """Комбинированный рейтинг"""
        return primary * 0.4 + behavioral * 0.6