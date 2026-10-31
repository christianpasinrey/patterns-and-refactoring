package orders

import (
	"context"

	"example.com/fulfilment/internal/ports"
)

type Order struct {
	ID       string
	Customer string
	Shipped  bool
}

type Service struct {
	Mailer ports.Mailer
}

func (s Service) Ship(ctx context.Context, order *Order) error {
	order.Shipped = true

	return s.Mailer.Send(ctx, order.Customer, "Your order shipped", "Order "+order.ID+" is on its way.")
}
