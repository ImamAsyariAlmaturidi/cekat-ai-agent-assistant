from chatkit.widgets import (
    ListView, ListViewItem, Col, Row, Card,
    Title, Text, Caption, Badge, Button, Icon,
    Divider, Spacer
)

# Enhanced pricing cards with better visual design
ListView(
    children=[
        ListViewItem(
            key=plan.id,
            gap=0,
            children=[
                Card(
                    padding=4,
                    radius="xl",
                    border=2 if plan.tag == "Popular" else 1,
                    background="surface" if not plan.tag else "primary-subtle",
                    children=[
                        Col(
                            gap=4,
                            children=[
                                # Header Section
                                Col(
                                    gap=2,
                                    children=[
                                        Row(
                                            align="center",
                                            justify="between",
                                            children=[
                                                Title(
                                                    value=plan.name,
                                                    size="xl",
                                                    weight="bold"
                                                ),
                                                Badge(
                                                    label=plan.tag,
                                                    color="primary",
                                                    variant="solid",
                                                    pill=True,
                                                    size="md"
                                                ) if plan.tag else None
                                            ]
                                        ),
                                        # Price Section
                                        Row(
                                            align="baseline",
                                            gap=1,
                                            children=[
                                                Caption(
                                                    value=plan.currency,
                                                    size="md",
                                                    color="secondary"
                                                ),
                                                Title(
                                                    value=plan.price,
                                                    size="4xl",
                                                    weight="bold",
                                                    color="primary"
                                                ),
                                                Text(
                                                    value=f"/ {plan.period}",
                                                    size="md",
                                                    color="secondary"
                                                )
                                            ]
                                        ),
                                        # Optional description
                                        Text(
                                            value=plan.description,
                                            size="sm",
                                            color="secondary",
                                            maxLines=2
                                        ) if hasattr(plan, 'description') else None
                                    ]
                                ),
                                
                                Divider(spacing=0),
                                
                                # Benefits Section
                                Col(
                                    gap=3,
                                    children=[
                                        Text(
                                            value="What's included:",
                                            size="sm",
                                            weight="semibold",
                                            color="secondary"
                                        ),
                                        Col(
                                            gap=2,
                                            children=[
                                                Row(
                                                    key=f"benefit-{idx}",
                                                    gap=2,
                                                    align="start",
                                                    children=[
                                                        Icon(
                                                            name="check-circle",
                                                            color="success",
                                                            size="md"
                                                        ),
                                                        Text(
                                                            value=benefit,
                                                            size="sm",
                                                            color="primary"
                                                        )
                                                    ]
                                                ) for idx, benefit in enumerate(plan.benefits)
                                            ]
                                        )
                                    ]
                                ),
                                
                                Spacer(),
                                
                                # CTA Button
                                Col(
                                    gap=2,
                                    children=[
                                        Button(
                                            label=plan.cta,
                                            style="primary" if plan.tag else "secondary",
                                            variant="solid",
                                            size="lg",
                                            block=True,
                                            pill=True,
                                            onClickAction={
                                                "type": "plan.subscribe",
                                                "payload": {
                                                    "id": plan.id,
                                                    "name": plan.name,
                                                    "currency": plan.currency,
                                                    "price": plan.price,
                                                    "period": plan.period,
                                                }
                                            }
                                        ),
                                        # Optional secondary action
                                        Button(
                                            label="Learn more",
                                            variant="ghost",
                                            size="md",
                                            block=True,
                                            color="secondary",
                                            onClickAction={
                                                "type": "plan.details",
                                                "payload": {"id": plan.id}
                                            }
                                        ) if hasattr(plan, 'has_details') and plan.has_details else None
                                    ]
                                )
                            ]
                        )
                    ]
                )
            ]
        ) for plan in plans
    ],
    limit="auto",
    theme="light"
)


# Alternative: Compact version for mobile/smaller screens
ListView(
    children=[
        ListViewItem(
            key=plan.id,
            gap=2,
            children=[
                Card(
                    padding=3,
                    radius="lg",
                    children=[
                        Row(
                            gap=3,
                            align="center",
                            children=[
                                # Left: Plan info
                                Col(
                                    gap=2,
                                    flex=1,
                                    children=[
                                        Row(
                                            align="center",
                                            gap=2,
                                            children=[
                                                Title(
                                                    value=plan.name,
                                                    size="lg",
                                                    weight="semibold"
                                                ),
                                                Badge(
                                                    label=plan.tag,
                                                    color="info",
                                                    size="sm",
                                                    pill=True
                                                ) if plan.tag else None
                                            ]
                                        ),
                                        Row(
                                            align="baseline",
                                            gap=1,
                                            children=[
                                                Caption(
                                                    value=plan.currency,
                                                    size="sm",
                                                    color="secondary"
                                                ),
                                                Title(
                                                    value=plan.price,
                                                    size="2xl",
                                                    weight="bold"
                                                ),
                                                Caption(
                                                    value=f"/{plan.period}",
                                                    size="md"
                                                )
                                            ]
                                        ),
                                        # Benefits count
                                        Text(
                                            value=f"{len(plan.benefits)} features included",
                                            size="xs",
                                            color="secondary"
                                        )
                                    ]
                                ),
                                
                                # Right: CTA
                                Button(
                                    label="Select",
                                    style="primary",
                                    size="md",
                                    pill=True,
                                    onClickAction={
                                        "type": "plan.subscribe",
                                        "payload": {
                                            "id": plan.id,
                                            "name": plan.name,
                                        }
                                    }
                                )
                            ]
                        )
                    ]
                )
            ]
        ) for plan in plans
    ]
)