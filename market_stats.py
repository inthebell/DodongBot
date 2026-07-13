import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median


DB_PATH = Path("market.db")
HOURS = 72
MIN_TRADES_FOR_OUTLIER_FILTER = 5


def normalize_item_name(name: str) -> str:
    return "".join(name.split()).lower()


def get_matching_items(
    connection: sqlite3.Connection,
    keyword: str,
) -> list[str]:
    normalized_keyword = normalize_item_name(keyword)

    rows = connection.execute(
        """
        SELECT DISTINCT item_name
        FROM trades
        ORDER BY item_name
        """
    ).fetchall()

    matched_items = []

    for row in rows:
        item_name = row[0]

        if normalized_keyword in normalize_item_name(item_name):
            matched_items.append(item_name)

    return matched_items


def calculate_quartiles(
    values: list[float],
) -> tuple[float, float]:
    sorted_values = sorted(values)
    count = len(sorted_values)
    middle = count // 2

    if count % 2 == 0:
        lower_half = sorted_values[:middle]
        upper_half = sorted_values[middle:]
    else:
        lower_half = sorted_values[:middle]
        upper_half = sorted_values[middle + 1:]

    q1 = median(lower_half)
    q3 = median(upper_half)

    return float(q1), float(q3)


def remove_outliers(
    rows: list[tuple],
) -> tuple[list[tuple], list[tuple]]:
    if len(rows) < MIN_TRADES_FOR_OUTLIER_FILTER:
        return rows, []

    unit_prices = [
        float(row[2])
        for row in rows
    ]

    q1, q3 = calculate_quartiles(unit_prices)
    iqr = q3 - q1

    lower_limit = q1 - (1.5 * iqr)
    upper_limit = q3 + (1.5 * iqr)

    included_rows = []
    excluded_rows = []

    for row in rows:
        unit_price = float(row[2])

        if lower_limit <= unit_price <= upper_limit:
            included_rows.append(row)
        else:
            excluded_rows.append(row)

    if not included_rows:
        return rows, []

    return included_rows, excluded_rows


def get_recent_rows(
    connection: sqlite3.Connection,
    item_name: str,
) -> list[tuple]:
    cutoff_date = datetime.now() - timedelta(
        hours=HOURS
    )

    return connection.execute(
        """
        SELECT
            quantity,
            total_price,
            unit_price,
            trade_date
        FROM trades
        WHERE item_name = ?
          AND trade_date >= ?
        ORDER BY trade_date ASC
        """,
        (
            item_name,
            cutoff_date.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        ),
    ).fetchall()


def get_latest_trade_row(
    connection: sqlite3.Connection,
    item_name: str,
) -> tuple | None:
    return connection.execute(
        """
        SELECT
            quantity,
            total_price,
            unit_price,
            trade_date
        FROM trades
        WHERE item_name = ?
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (
            item_name,
        ),
    ).fetchone()


def build_recent_stats(
    item_name: str,
    rows: list[tuple],
) -> dict:
    included_rows, excluded_rows = remove_outliers(
        rows
    )

    quantities = [
        int(row[0])
        for row in included_rows
    ]

    unit_prices = [
        float(row[2])
        for row in included_rows
    ]

    trade_dates = [
        datetime.strptime(
            row[3],
            "%Y-%m-%d %H:%M:%S",
        )
        for row in included_rows
    ]

    representative_quantity = Counter(
        quantities
    ).most_common(1)[0][0]

    representative_rows = [
        row
        for row in included_rows
        if int(row[0]) == representative_quantity
    ]

    representative_totals = [
        int(row[1])
        for row in representative_rows
    ]

    return {
        "mode": "recent",
        "item_name": item_name,
        "average_unit_price": round(
            sum(unit_prices) / len(unit_prices)
        ),
        "minimum_unit_price": round(
            min(unit_prices)
        ),
        "maximum_unit_price": round(
            max(unit_prices)
        ),
        "representative_quantity": representative_quantity,
        "average_total": round(
            sum(representative_totals)
            / len(representative_totals)
        ),
        "minimum_total": min(
            representative_totals
        ),
        "maximum_total": max(
            representative_totals
        ),
        "original_trade_count": len(rows),
        "used_trade_count": len(included_rows),
        "excluded_trade_count": len(excluded_rows),
        "first_trade_date": min(trade_dates),
        "latest_trade_date": max(trade_dates),
    }


def build_last_trade_stats(
    item_name: str,
    row: tuple,
) -> dict:
    quantity = int(row[0])
    total_price = int(row[1])
    unit_price = float(row[2])

    trade_date = datetime.strptime(
        row[3],
        "%Y-%m-%d %H:%M:%S",
    )

    return {
        "mode": "last_trade",
        "item_name": item_name,
        "unit_price": round(unit_price),
        "quantity": quantity,
        "total_price": total_price,
        "latest_trade_date": trade_date,
    }


def get_item_stats(
    connection: sqlite3.Connection,
    item_name: str,
) -> dict | None:
    recent_rows = get_recent_rows(
        connection,
        item_name,
    )

    if recent_rows:
        return build_recent_stats(
            item_name,
            recent_rows,
        )

    latest_row = get_latest_trade_row(
        connection,
        item_name,
    )

    if latest_row is None:
        return None

    return build_last_trade_stats(
        item_name,
        latest_row,
    )


def format_days_ago(trade_date: datetime) -> str:
    now = datetime.now()
    difference = now - trade_date

    if difference.total_seconds() < 0:
        return "방금 전"

    days = difference.days

    if days == 0:
        hours = difference.seconds // 3600

        if hours == 0:
            minutes = difference.seconds // 60

            if minutes <= 0:
                return "방금 전"

            return f"{minutes}분 전"

        return f"{hours}시간 전"

    if days == 1:
        return "1일 전"

    return f"{days}일 전"


def print_recent_stats(stats: dict) -> None:
    print()
    print("=" * 60)
    print(f"💰 {stats['item_name']} 시세")
    print()

    print("개당 평균가")
    print(f"{stats['average_unit_price']:,}냥")
    print()

    print(
        f"📦 {stats['representative_quantity']}개 기준"
    )
    print(
        f"평균 {stats['average_total']:,}냥"
    )
    print(
        f"범위 "
        f"{stats['minimum_total']:,}"
        f" ~ "
        f"{stats['maximum_total']:,}냥"
    )
    print()

    print("📊 거래 정보")
    print(
        f"거래 범위 "
        f"{stats['minimum_unit_price']:,}"
        f" ~ "
        f"{stats['maximum_unit_price']:,}냥"
    )
    print(
        f"거래 건수 "
        f"{stats['used_trade_count']}건"
    )
    print(
        "최근 거래 "
        f"{stats['latest_trade_date'].strftime('%Y-%m-%d %H:%M')}"
    )

    if stats["excluded_trade_count"] > 0:
        print()
        print(
            f"※ 이상치 "
            f"{stats['excluded_trade_count']}건 제외"
        )

    print()
    print("※ 통합거래소 구매 완료 내역 기준")
    print("※ 최근 최대 72시간 데이터로 계산")

    if stats["used_trade_count"] <= 4:
        print()
        print(
            f"⚠️ 거래 데이터가 "
            f"{stats['used_trade_count']}건으로 적습니다."
        )
        print(
            "시세 참고 후 신중하게 거래해주세요."
        )

    print("=" * 60)


def print_last_trade_stats(stats: dict) -> None:
    latest_trade_date = stats["latest_trade_date"]

    print()
    print("=" * 60)
    print(f"💰 {stats['item_name']} 시세")
    print()

    print("최근 거래 시세")
    print()

    print("개당 가격")
    print(f"{stats['unit_price']:,}냥")
    print()

    print(
        f"📦 {stats['quantity']}개 기준"
    )
    print(f"{stats['total_price']:,}냥")
    print()

    print("📅 마지막 거래")
    print(
        latest_trade_date.strftime(
            "%Y-%m-%d %H:%M"
        )
    )
    print(
        f"({format_days_ago(latest_trade_date)})"
    )
    print()

    print(
        "⚠️ 최근 72시간 동안 거래 내역이 없습니다."
    )
    print(
        "최근 거래를 참고해주세요."
    )
    print()

    print("※ 통합거래소 구매 완료 내역 기준")
    print("=" * 60)


def print_item_stats(stats: dict) -> None:
    if stats["mode"] == "recent":
        print_recent_stats(stats)
        return

    print_last_trade_stats(stats)


def select_item(
    matched_items: list[str],
) -> str | None:
    if len(matched_items) == 1:
        return matched_items[0]

    print()
    print("여러 아이템이 검색되었습니다.")

    for index, item_name in enumerate(
        matched_items,
        start=1,
    ):
        print(f"{index}. {item_name}")

    selection = input(
        "번호를 선택하세요: "
    ).strip()

    if not selection.isdigit():
        print("번호를 입력해주세요.")
        return None

    selected_index = int(selection) - 1

    if (
        selected_index < 0
        or selected_index >= len(matched_items)
    ):
        print("올바른 번호를 입력해주세요.")
        return None

    return matched_items[selected_index]


def main() -> None:
    connection = sqlite3.connect(DB_PATH)

    print("=" * 60)
    print("통합거래소 평균 시세 검색")
    print("띄어쓰기를 무시하고 부분 검색합니다.")
    print("종료하려면 exit를 입력하세요.")
    print("=" * 60)

    while True:
        keyword = input(
            "\n아이템명 검색: "
        ).strip()

        if keyword.lower() == "exit":
            break

        if not keyword:
            continue

        matched_items = get_matching_items(
            connection,
            keyword,
        )

        if not matched_items:
            print()
            print("🔎 시세 정보를 찾을 수 없습니다.")
            print()
            print("아이템명을 다시 확인해주세요.")
            print(
                "예: 레몬, 셜커, 주괴"
            )
            print()
            print(
                "※ 최근 거래 내역이 없거나 아직 "
                "수집되지 않은 아이템은 "
                "조회되지 않을 수 있습니다."
            )
            continue

        selected_item = select_item(
            matched_items,
        )

        if selected_item is None:
            continue

        stats = get_item_stats(
            connection,
            selected_item,
        )

        if stats is None:
            print()
            print("🔎 시세 정보를 찾을 수 없습니다.")
            continue

        print_item_stats(stats)

    connection.close()


if __name__ == "__main__":
    main()