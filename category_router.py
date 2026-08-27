"""
상품 카테고리/이름 키워드로 실사(모델 착용) vs 제품샷 방식을 분기
"""

# 카테고리명이 아니라 "몸에 착용/휴대하는 형태가 보여야 매력적인 물건"인지로 판단.
# 패션잡화 카테고리라도 소모품/세척용품/액세서리 부자재는 제외.
WEARABLE_KEYWORDS = [
    "신발", "슈즈", "운동화", "구두", "샌들", "슬리퍼",
    "양말", "삭스", "스타킹",
    "가방", "백팩", "숄더백", "크로스백", "파우치",
    "머리띠", "헤어밴드", "머리끈",
    "시계", "손목시계",
    "안경", "선글라스",
    "목도리", "머플러", "스카프", "넥쿨러",
    "장갑", "토시",
    "니트", "코트", "자켓", "재킷", "원피스", "티셔츠", "셔츠", "바지",
    "청바지", "가디건", "후드", "맨투맨", "패딩", "조끼",
]

# 착용 키워드가 있어도 소모품/세척/보관용은 제외
EXCLUDE_KEYWORDS = [
    "클리너", "세척", "세정", "방지 용액", "패드", "파우치 10개", "수선",
    "안티포그", "케이스만", "충전기", "보호대",
]


def should_use_realistic(category_name: str, product_name: str) -> bool:
    text = f"{category_name} {product_name}"
    if any(kw in text for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in text for kw in WEARABLE_KEYWORDS)
