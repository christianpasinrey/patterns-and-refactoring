package smtp

import (
	"context"
	"fmt"
	"net/smtp"
)

type Mailer struct {
	Addr string
	From string
}

func (m Mailer) Send(_ context.Context, to, subject, body string) error {
	msg := fmt.Sprintf("Subject: %s\r\n\r\n%s", subject, body)
	return smtp.SendMail(m.Addr, nil, m.From, []string{to}, []byte(msg))
}
